"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.context.package_models import ContextPackage, RepositorySummary
from app.core.models import IndexingReport
from app.services.options import BuildOptions


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | list | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    providers: dict[str, str]


class IndexRequest(BaseModel):
    path: str = Field(
        ..., min_length=1, max_length=4096, description="Local directory inside an allowed root"
    )


class IndexResponse(BaseModel):
    repository: RepositorySummary
    report: IndexingReport


class FileInfo(BaseModel):
    path: str
    file_type: str
    language: str
    tokens: int
    line_count: int
    symbol_count: int = 0
    parse_error: str | None = None


class SymbolInfo(BaseModel):
    id: str
    qualname: str
    kind: str
    signature: str
    start_line: int
    end_line: int
    docstring: str | None = None


class RepositoryResponse(BaseModel):
    repository: RepositorySummary
    report: IndexingReport
    files: list[FileInfo] | None = None
    symbols: dict[str, list[SymbolInfo]] | None = None
    graph: dict | None = None


class ExampleRepository(BaseModel):
    name: str
    path: str
    description: str


class ConfigResponse(BaseModel):
    """Defaults the frontend uses to populate its forms."""

    sample_repository_path: str
    example_repositories: list[ExampleRepository] = Field(default_factory=list)
    budget: dict
    weights: dict[str, float]
    expansion_depth: int
    modes: dict[str, str]
    tokenizer_encoding: str
    providers: dict[str, str]


class RunInfo(BaseModel):
    timestamp: float
    repository_id: str
    task: str
    mode: str
    selected_files: int
    rendered_tokens: int
    usable_tokens: int
    latency_ms: float


class BuildRequest(BuildOptions):
    repository_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class CompareRequest(BuildRequest):
    relevant_paths: list[str] = Field(default_factory=list, max_length=200)
    k: int = Field(5, ge=1, le=50)


class ExportRequest(BaseModel):
    format: Literal["markdown", "json", "txt"]
    package: ContextPackage | None = None
    build: BuildRequest | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> ExportRequest:
        if (self.package is None) == (self.build is None):
            raise ValueError("provide exactly one of 'package' or 'build'")
        return self


class ExportResponse(BaseModel):
    format: str
    filename: str
    mime_type: str
    content: str


class BenchmarkRunRequest(BaseModel):
    token_budget: int = Field(4000, ge=1000, le=200_000)
    k: int = Field(5, ge=1, le=20)


# ------------------------------------------------------------------- accounts
class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(None, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    display_name: str
    email: str | None = None
    github_login: str | None = None
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_minutes: int
    user: UserOut


class AuthProviders(BaseModel):
    email_password: bool = True
    github: bool
    require_auth: bool
    database: str


class SavePackageRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    package: ContextPackage


class SavedPackageSummary(BaseModel):
    id: int
    title: str
    task: str
    repository_name: str
    item_count: int
    rendered_tokens: int
    created_at: datetime


class SavedPackageOut(SavedPackageSummary):
    package: ContextPackage


class ConversationBenchmarkRequest(BaseModel):
    mode: Literal["dry-run", "live"] = Field(
        "dry-run", description="dry-run uses mock models; live calls the configured models"
    )
    budget_tokens: int | None = Field(
        None, ge=1000, le=16000, description="Token budget (default: config.yaml)"
    )


class ConversationModelStatus(BaseModel):
    backend: str
    model: str
    real_model: bool = Field(description="True when a real model will be called")
    status: str


class ConversationStatus(BaseModel):
    manager: ConversationModelStatus
    main_model: ConversationModelStatus
    live_runs_enabled: bool
    live_available: bool
    default_budget_tokens: int
    context: dict
