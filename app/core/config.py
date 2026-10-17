"""Application configuration.

Settings come from (in increasing priority): defaults, environment variables
(optionally loaded from a local ``.env`` file), and per-request overrides.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_REPO_PATH = PROJECT_ROOT / "examples" / "sample_fastapi_repo"
BENCHMARK_FILE = PROJECT_ROOT / "benchmarks" / "sample_fastapi_tasks.json"


class RankingWeights(BaseModel):
    """Weights for the hybrid ranker. Each signal is normalised to [0, 1] before weighting."""

    lexical: float = Field(0.35, ge=0, le=10)
    filename: float = Field(0.10, ge=0, le=10)
    symbol: float = Field(0.15, ge=0, le=10)
    dependency: float = Field(0.20, ge=0, le=10)
    test: float = Field(0.10, ge=0, le=10)
    config: float = Field(0.05, ge=0, le=10)
    semantic: float = Field(0.0, ge=0, le=10)

    def total(self) -> float:
        return sum(self.model_dump().values())


class BudgetSettings(BaseModel):
    total_tokens: int = Field(8000, ge=500, le=2_000_000)
    reserved_system_tokens: int = Field(400, ge=0)
    reserved_response_tokens: int = Field(1500, ge=0)
    safety_margin_ratio: float = Field(0.05, ge=0, le=0.5)
    per_item_overhead_tokens: int = Field(24, ge=0, le=500)


class Settings(BaseModel):
    """Global ACWM settings. Immutable per request: copy with ``model_copy(update=...)``."""

    allowed_roots: list[Path] = Field(default_factory=lambda: [PROJECT_ROOT])
    tokenizer_encoding: str = "cl100k_base"
    max_file_bytes: int = Field(1_000_000, ge=1_000)
    max_files: int = Field(5_000, ge=1)
    max_total_bytes: int = Field(50_000_000, ge=10_000)
    extra_excluded_dirs: list[str] = Field(default_factory=list)
    extra_excluded_globs: list[str] = Field(default_factory=list)
    respect_gitignore: bool = True
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    weights: RankingWeights = Field(default_factory=RankingWeights)
    expansion_depth: int = Field(2, ge=0, le=5)
    # LLM (optional)
    llm_provider: str = "none"  # "none" | "anthropic"
    llm_model: str = "claude-opus-5-5"
    llm_timeout_seconds: float = Field(30.0, gt=0, le=600)
    # TinyFish (optional)
    tinyfish_enabled: bool = False
    tinyfish_timeout_seconds: float = Field(20.0, gt=0, le=150)
    tinyfish_include_domains: list[str] = Field(
        default_factory=lambda: [
            "fastapi.tiangolo.com",
            "docs.pydantic.dev",
            "docs.python.org",
            "www.starlette.io",
        ]
    )
    # API limits
    api_max_request_bytes: int = Field(1_000_000, ge=1_000)
    api_timeout_seconds: float = Field(60.0, gt=0, le=600)
    api_max_sessions: int = Field(200, ge=1, le=10_000)
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ]
    )
    # Matches the Render static-site URL even if Render appends a suffix to the name.
    cors_origin_regex: str | None = r"https://acwm-web(-[a-z0-9]+)?\.onrender\.com"

    @field_validator("allowed_roots", mode="before")
    @classmethod
    def _resolve_roots(cls, value: list) -> list[Path]:
        return [Path(v).expanduser().resolve() for v in value]


def _split_list(raw: str | None, sep: str) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(sep) if part.strip()]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env_file: Path | None = None) -> Settings:
    """Build settings from the environment. Never logs secret values."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    data: dict = {}
    roots = _split_list(os.getenv("ACWM_ALLOWED_ROOTS"), os.pathsep)
    data["allowed_roots"] = [PROJECT_ROOT, *roots]
    if enc := os.getenv("ACWM_TOKENIZER_ENCODING"):
        data["tokenizer_encoding"] = enc
    if raw := os.getenv("ACWM_MAX_FILE_BYTES"):
        data["max_file_bytes"] = int(raw)
    if raw := os.getenv("ACWM_MAX_FILES"):
        data["max_files"] = int(raw)
    budget = {}
    if raw := os.getenv("ACWM_TOKEN_BUDGET"):
        budget["total_tokens"] = int(raw)
    if raw := os.getenv("ACWM_RESERVED_RESPONSE_TOKENS"):
        budget["reserved_response_tokens"] = int(raw)
    if budget:
        data["budget"] = BudgetSettings(**budget)
    data["llm_provider"] = os.getenv("ACWM_LLM_PROVIDER", "none").strip().lower()
    if model := os.getenv("ACWM_LLM_MODEL"):
        data["llm_model"] = model
    data["tinyfish_enabled"] = _env_bool("ACWM_TINYFISH_ENABLED", False)
    if domains := _split_list(os.getenv("ACWM_TINYFISH_INCLUDE_DOMAINS"), ","):
        data["tinyfish_include_domains"] = domains
    if origins := _split_list(os.getenv("ACWM_CORS_ORIGINS"), ","):
        data["cors_origins"] = origins
    if (regex := os.getenv("ACWM_CORS_ORIGIN_REGEX")) is not None:
        data["cors_origin_regex"] = regex or None
    return Settings(**data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
