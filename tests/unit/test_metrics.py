import pytest

from app.evaluation.metrics import coverage, mean, precision_at_k, recall_at_k, reciprocal_rank

RANKED = ["a", "x", "b", "y", "c"]
RELEVANT = {"a", "b", "c", "d"}


def test_precision_recall_mrr():
    assert precision_at_k(RANKED, RELEVANT, 2) == 0.5
    assert precision_at_k(RANKED, RELEVANT, 5) == 0.6
    assert precision_at_k(["a"], RELEVANT, 5) == 1.0  # fewer selected than K
    assert recall_at_k(RANKED, RELEVANT, 5) == 0.75
    assert reciprocal_rank(["x", "y", "b"], RELEVANT) == pytest.approx(1 / 3)
    assert reciprocal_rank(["x"], RELEVANT) == 0.0


def test_undefined_metrics_are_none():
    assert precision_at_k([], RELEVANT, 5) is None
    assert recall_at_k(RANKED, set(), 5) is None
    assert reciprocal_rank([], RELEVANT) is None
    assert coverage({"a"}, set()) is None
    assert mean([None, None]) is None


def test_coverage_and_mean():
    assert coverage({"a", "b", "z"}, RELEVANT) == 0.5
    assert mean([1.0, None, 0.0]) == 0.5
