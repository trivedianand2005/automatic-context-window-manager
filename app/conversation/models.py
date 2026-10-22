"""Data models for the conversation manager, including the manager LLM's output schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant"]
CompactionMode = Literal["llm", "heuristic"]


class Message(BaseModel):
    """One conversation message plus the metadata tracked every turn (no LLM involved)."""

    id: str
    role: Role
    content: str
    turn: int
    timestamp: float
    tokens: int
    pinned: bool = False
    score: int | None = Field(None, description="Importance 1-5, set at compaction time")


class Fact(BaseModel):
    """A durable fact kept in the pinned-facts block. Facts are never evicted."""

    text: str
    turn: int = Field(description="Turn at which the fact was last learned or updated")
    key: str | None = Field(None, description="Topic before ':'; same key = newer fact wins")


class MessageScore(BaseModel):
    id: str
    score: int = Field(ge=1, le=5)
    reason: str = ""


class ManagerOutput(BaseModel):
    """What the manager LLM must return. Every response is validated against this."""

    summary: str
    pinned_facts: list[str]
    message_scores: list[MessageScore]
    superseded: list[str] = Field(default_factory=list)


# JSON Schema sent to the backend (Anthropic structured outputs / Ollama ``format``).
# Range checks (score 1-5) are enforced by ManagerOutput after parsing.
MANAGER_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "pinned_facts": {"type": "array", "items": {"type": "string"}},
        "message_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "score", "reason"],
                "additionalProperties": False,
            },
        },
        "superseded": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "pinned_facts", "message_scores", "superseded"],
    "additionalProperties": False,
}


class CompactionReport(BaseModel):
    turn: int
    mode: CompactionMode
    tokens_before: int
    tokens_after: int
    summarized_ids: list[str] = Field(default_factory=list)
    kept_verbatim_ids: list[str] = Field(default_factory=list)
    evicted_ids: list[str] = Field(default_factory=list)
    manager_calls: int = 0
    manager_input_tokens: int = 0
    manager_output_tokens: int = 0
    manager_latency_ms: float = 0.0
    manager_cost_usd: float = 0.0
    error: str | None = None


class TurnMetrics(BaseModel):
    """Per-turn instrumentation for the demo and benchmark."""

    turn: int
    context_tokens: int
    usage_ratio: float
    main_model: str
    main_input_tokens: int
    main_output_tokens: int
    main_cost_usd: float
    manager_calls: int = 0
    manager_input_tokens: int = 0
    manager_output_tokens: int = 0
    manager_latency_ms: float = 0.0
    manager_cost_usd: float = 0.0
    compaction: CompactionMode | None = None

    @property
    def total_cost_usd(self) -> float:
        return self.main_cost_usd + self.manager_cost_usd
