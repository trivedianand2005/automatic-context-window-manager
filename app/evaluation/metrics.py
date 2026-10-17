"""Retrieval metrics. Each returns ``None`` (reported as N/A) when undefined.

ranked:   paths in the order the method ranks its *selected* context items
relevant: manually labelled ground-truth relevant paths

precision@K  = |relevant ∩ ranked[:K]| / min(K, |ranked|)   (N/A if nothing selected)
recall@K     = |relevant ∩ ranked[:K]| / |relevant|           (N/A if no labels)
MRR          = 1 / rank of first relevant item (0 if none)    (N/A if nothing selected)
coverage     = |relevant ∩ selected| / |relevant|, counting partial excerpts as covered
full_coverage= same, but only files included in full
"""

from __future__ import annotations


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float | None:
    if not ranked or k <= 0:
        return None
    top = ranked[:k]
    return sum(1 for p in top if p in relevant) / len(top)


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float | None:
    if not relevant:
        return None
    return sum(1 for p in ranked[:k] if p in relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float | None:
    if not ranked:
        return None
    for i, p in enumerate(ranked, start=1):
        if p in relevant:
            return 1.0 / i
    return 0.0


def coverage(selected: set[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    return len(selected & relevant) / len(relevant)


def mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None
