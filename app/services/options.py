"""Request options shared by the service layer, FastAPI and Streamlit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import RankingWeights

RetrievalMode = Literal["acwm", "dependency", "baseline"]
CompressionMode = Literal["extractive", "llm", "none"]

MODE_LABELS = {
    "baseline": "Baseline (BM25 only, whole files in rank order)",
    "dependency": "BM25 + dependency expansion (whole files in rank order)",
    "acwm": "Full ACWM (hybrid ranking + budget optimizer + compression)",
}


class BuildOptions(BaseModel):
    task: str = Field(..., min_length=3, max_length=4000)
    mode: RetrievalMode = "acwm"
    token_budget: int | None = Field(None, ge=500, le=2_000_000)
    reserved_response_tokens: int | None = Field(None, ge=0, le=200_000)
    weights: RankingWeights | None = None
    expansion_depth: int | None = Field(None, ge=0, le=5)
    compression: CompressionMode = "extractive"
    use_semantic: bool = False
    use_llm_analysis: bool = False
    include_research: bool = False
    redundancy_penalty: bool = True
    required_paths: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("task")
    @classmethod
    def _strip_task(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("task must contain at least 3 non-whitespace characters")
        return v
