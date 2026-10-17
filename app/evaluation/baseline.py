"""Rank-order selection used by the baseline and dependency-expansion comparison modes.

Both comparison methods take whole files in rank order and skip files that do not
fit the remaining budget. No excerpts, no relevance-per-token, no redundancy logic.
This isolates the effect of ACWM's optimizer from the effect of ranking signals.
"""

from __future__ import annotations

from app.context.budget_optimizer import OptimizationResult, Selection
from app.context.token_counter import BudgetPlan, TokenCounter
from app.core.models import Candidate, RepoFile


def rank_order_select(
    candidates: list[Candidate],
    files: dict[str, RepoFile],
    plan: BudgetPlan,
    counter: TokenCounter,
    max_items: int | None = None,
) -> OptimizationResult:
    result = OptimizationResult()
    for rank, cand in enumerate(candidates, start=1):
        f = files[cand.path]
        cost = counter.count(f.content) + plan.per_item_overhead_tokens
        if max_items is not None and len(result.selected) >= max_items:
            result.excluded.append((cand, f"beyond max_items={max_items}"))
            continue
        if result.used_tokens + cost > plan.usable_tokens:
            result.excluded.append(
                (
                    cand,
                    f"rank {rank}: full file ({cost} tokens) does not fit remaining "
                    f"{plan.usable_tokens - result.used_tokens} tokens",
                )
            )
            continue
        result.selected.append(
            Selection(
                cand,
                "full",
                f.content,
                cost,
                [(1, f.line_count)] if f.line_count else [],
                [],
                f"rank {rank} by score {cand.combined:.3f}; full file ({cost} tokens)",
            )
        )
        result.used_tokens += cost
    return result
