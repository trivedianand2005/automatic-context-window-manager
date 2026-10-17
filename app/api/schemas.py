"""Pydantic request/response models for the REST API."""

from __future__ import annotations

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


class RepositoryResponse(BaseModel):
    repository: RepositorySummary
    report: IndexingReport
    symbols: dict[str, list[str]] | None = None
    graph: dict | None = None


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
