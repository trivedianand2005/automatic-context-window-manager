"""Shared domain models used by the service layer, API and UI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FileType = Literal["source", "test", "config", "docs", "other"]
Confidence = Literal["high", "medium", "low"]


class RepoFile(BaseModel):
    path: str  # repository-relative POSIX path
    language: str
    file_type: FileType
    size_bytes: int
    sha256: str
    tokens: int
    content: str = Field(repr=False)
    line_count: int


class ExcludedFile(BaseModel):
    path: str
    reason: str


class IndexingReport(BaseModel):
    root: str
    total_discovered: int = 0
    indexed: int = 0
    skipped: int = 0
    excluded: list[ExcludedFile] = Field(default_factory=list)
    file_types: dict[str, int] = Field(default_factory=dict)
    languages: dict[str, int] = Field(default_factory=dict)
    total_tokens: int = 0
    total_bytes: int = 0
    parse_warnings: list[str] = Field(default_factory=list)
    limit_reached: str | None = None
    tokenizer: str = ""
    duration_ms: float = 0.0


class Symbol(BaseModel):
    id: str  # "<path>::<qualname>"
    name: str
    qualname: str
    kind: Literal["function", "async_function", "class", "method", "async_method"]
    path: str
    module: str
    signature: str
    docstring: str | None = None
    start_line: int
    end_line: int
    parent: str | None = None  # qualname of enclosing symbol
    decorators: list[str] = Field(default_factory=list)


class ImportRef(BaseModel):
    module: str  # as written (without leading dots)
    names: list[str] = Field(default_factory=list)
    level: int = 0  # number of leading dots for relative imports
    line: int
    is_from: bool = False
    conditional: bool = False  # inside if/try
    type_checking: bool = False  # inside `if TYPE_CHECKING:`


class ResolvedImport(BaseModel):
    source_path: str
    raw: str
    target_path: str | None = None
    status: Literal["local", "external", "unresolved"]
    confidence: Confidence = "high"
    line: int
    note: str = ""


class ModuleInfo(BaseModel):
    path: str
    module: str
    docstring: str | None = None
    symbols: list[Symbol] = Field(default_factory=list)
    imports: list[ImportRef] = Field(default_factory=list)
    parse_error: str | None = None


class TaskAnalysis(BaseModel):
    task: str
    keywords: list[str]
    technical_terms: list[str]
    component_names: list[str]
    expanded_terms: list[str]
    file_type_hints: list[str]
    wants_tests: bool
    config_terms: list[str]
    analyzer: str = "deterministic"
    notes: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    lexical: float = 0.0
    filename: float = 0.0
    symbol: float = 0.0
    dependency: float = 0.0
    test: float = 0.0
    config: float = 0.0
    semantic: float = 0.0


class Candidate(BaseModel):
    path: str
    file_type: FileType
    language: str
    tokens: int
    raw_bm25: float = 0.0
    scores: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    combined: float = 0.0
    matched_terms: list[str] = Field(default_factory=list)
    matched_symbols: list[str] = Field(default_factory=list)  # symbol ids
    dependency_path: list[str] = Field(default_factory=list)
    dependency_relation: str | None = None
    dependency_confidence: Confidence | None = None
    reasons: list[str] = Field(default_factory=list)
