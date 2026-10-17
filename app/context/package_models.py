"""Schema for exported context packages (validated on export)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.models import ScoreBreakdown, TaskAnalysis

SCHEMA_VERSION = "1.0"
DISCLAIMER = (
    "This package was assembled by static analysis and lexical/graph heuristics. It may "
    "omit relevant code (dynamic imports, runtime wiring, non-Python files) and does not "
    "guarantee that changes based on it are correct. Token counts are estimates."
)

ItemKind = Literal["full", "excerpt", "outline", "summary"]


class ContextItem(BaseModel):
    path: str
    kind: ItemKind
    is_partial: bool
    language: str
    file_type: str
    line_ranges: list[tuple[int, int]] = Field(default_factory=list)
    total_lines: int
    symbols: list[str] = Field(default_factory=list)
    tokens: int = Field(description="Estimated tokens of content + per-item overhead")
    full_file_tokens: int
    combined_score: float
    scores: ScoreBreakdown
    reasons: list[str] = Field(default_factory=list)
    selection_note: str = ""
    required: bool = False
    dependency_path: list[str] = Field(default_factory=list)
    content: str


class ExcludedCandidate(BaseModel):
    path: str
    tokens: int
    combined_score: float
    reason: str


class DependencyEdge(BaseModel):
    source: str
    target: str
    relation: str
    confidence: str


class ResearchFinding(BaseModel):
    title: str
    url: str
    snippet: str
    source: str
    provider_status: str


class TokenStats(BaseModel):
    tokenizer: str
    exact_for_target_model: bool = False
    total_indexed_tokens: int
    candidate_tokens: int
    selected_tokens: int
    rendered_context_tokens: int
    total_budget: int
    reserved_system_tokens: int
    reserved_task_tokens: int
    reserved_response_tokens: int
    safety_margin_tokens: int
    usable_tokens: int
    remaining_tokens: int
    utilization: float
    reduction_vs_full_repository: float | None = None
    reduction_vs_baseline: float | None = None


class RepositorySummary(BaseModel):
    repository_id: str
    root_name: str
    fingerprint: str
    indexed_files: int
    languages: dict[str, int]
    file_types: dict[str, int]
    total_tokens: int
    module_count: int
    symbol_count: int
    dependency_edges: int


class RetrievalConfig(BaseModel):
    mode: str
    weights: dict[str, float]
    expansion_depth: int
    compression: str
    semantic: str
    llm: str
    analyzer: str
    required_paths: list[str] = Field(default_factory=list)


class ContextPackage(BaseModel):
    schema_version: str = SCHEMA_VERSION
    task: str
    analysis: TaskAnalysis
    repository: RepositorySummary
    configuration: RetrievalConfig
    items: list[ContextItem]
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)
    excluded: list[ExcludedCandidate] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    token_stats: TokenStats
    research_findings: list[ResearchFinding] = Field(default_factory=list)
    latency_ms: float = 0.0
    disclaimer: str = DISCLAIMER
