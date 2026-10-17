"""Token estimation service.

ACWM uses ``tiktoken`` with an explicit encoding (default ``cl100k_base``). These
counts are *estimates*: the model that eventually consumes the context package may
use a different tokenizer (Claude models, for example, do not use tiktoken
encodings), so counts can differ by a noticeable margin. A safety margin is
reserved in the budget plan for that reason.

If tiktoken or the requested encoding cannot be loaded (e.g. offline first run),
a conservative character heuristic is used and flagged via ``method``/``warnings``.
"""

from __future__ import annotations

import math
from functools import lru_cache

from pydantic import BaseModel, Field

from app.core.config import BudgetSettings

SUPPORTED_ENCODINGS = ["cl100k_base", "o200k_base", "p50k_base"]
HEURISTIC_CHARS_PER_TOKEN = 3.0  # deliberately conservative (over-estimates)


class TokenCounter:
    def __init__(self, encoding: str = "cl100k_base") -> None:
        self.encoding_name = encoding
        self.method = "tiktoken"
        self.warnings: list[str] = [
            f"Token counts are tiktoken '{encoding}' estimates, not authoritative counts from "
            "the target model's tokenizer."
        ]
        self._encoder = _load_encoder(encoding)
        if self._encoder is None:
            self.method = "heuristic"
            self.warnings.append(
                f"tiktoken encoding '{encoding}' unavailable; using a conservative "
                f"{HEURISTIC_CHARS_PER_TOKEN} chars/token heuristic."
            )

    @property
    def is_exact_for_encoding(self) -> bool:
        return self._encoder is not None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoder is not None:
            return len(self._encoder.encode(text, disallowed_special=()))
        return math.ceil(len(text) / HEURISTIC_CHARS_PER_TOKEN)

    def truncate(self, text: str, max_tokens: int) -> str:
        """Truncate text to at most ``max_tokens`` tokens (used only for previews/LLM input)."""
        if max_tokens <= 0:
            return ""
        if self._encoder is not None:
            ids = self._encoder.encode(text, disallowed_special=())
            return text if len(ids) <= max_tokens else self._encoder.decode(ids[:max_tokens])
        return text[: int(max_tokens * HEURISTIC_CHARS_PER_TOKEN)]


@lru_cache(maxsize=8)
def _load_encoder(encoding: str):
    try:
        import tiktoken

        return tiktoken.get_encoding(encoding)
    except Exception:  # noqa: BLE001 - any failure falls back to the heuristic
        return None


@lru_cache(maxsize=8)
def get_token_counter(encoding: str = "cl100k_base") -> TokenCounter:
    return TokenCounter(encoding)


class BudgetPlan(BaseModel):
    total_tokens: int
    reserved_system_tokens: int
    reserved_task_tokens: int
    reserved_response_tokens: int
    safety_margin_tokens: int
    per_item_overhead_tokens: int
    usable_tokens: int = Field(description="Tokens available for selected repository context")

    @property
    def reserved_total(self) -> int:
        return (
            self.reserved_system_tokens
            + self.reserved_task_tokens
            + self.reserved_response_tokens
            + self.safety_margin_tokens
        )


def plan_budget(budget: BudgetSettings, task_text: str, counter: TokenCounter) -> BudgetPlan:
    """Compute the usable context budget after reservations.

    The task itself is always reserved (it is never dropped to make room for code).
    """
    task_tokens = counter.count(task_text) + 16  # heading/formatting overhead
    margin = math.ceil(budget.total_tokens * budget.safety_margin_ratio)
    usable = (
        budget.total_tokens
        - budget.reserved_system_tokens
        - task_tokens
        - budget.reserved_response_tokens
        - margin
    )
    return BudgetPlan(
        total_tokens=budget.total_tokens,
        reserved_system_tokens=budget.reserved_system_tokens,
        reserved_task_tokens=task_tokens,
        reserved_response_tokens=budget.reserved_response_tokens,
        safety_margin_tokens=margin,
        per_item_overhead_tokens=budget.per_item_overhead_tokens,
        usable_tokens=max(0, usable),
    )
