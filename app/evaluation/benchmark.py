"""Benchmark dataset loading and aggregation (used by ACWMService.run_benchmarks)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from app.evaluation import metrics

MODES = ("baseline", "dependency", "acwm")


class BenchmarkTask(BaseModel):
    id: str
    task: str
    relevant: list[str]
    rationale: str = ""


def load_benchmark(path: Path) -> tuple[str, list[BenchmarkTask]]:
    """Return (repository path relative to the project root, labelled tasks)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["repository"], [BenchmarkTask(**t) for t in data["tasks"]]


def aggregate(method_rows: dict[str, list], k: int) -> dict[str, dict[str, float | None]]:
    """Mean of each metric per mode. ``method_rows[mode]`` holds MethodResult objects."""
    out: dict[str, dict[str, float | None]] = {}
    for mode, rows in method_rows.items():
        out[mode] = {
            f"precision@{k}": metrics.mean([m.precision_at_k for m in rows]),
            f"recall@{k}": metrics.mean([m.recall_at_k for m in rows]),
            "mrr": metrics.mean([m.mrr for m in rows]),
            "coverage": metrics.mean([m.coverage for m in rows]),
            "full_coverage": metrics.mean([m.full_coverage for m in rows]),
            "mean_rendered_tokens": metrics.mean([float(m.rendered_tokens) for m in rows]),
            "mean_utilization": metrics.mean([m.utilization for m in rows]),
            "budget_violations": float(sum(m.budget_violation for m in rows)),
            "mean_latency_ms": metrics.mean([m.latency_ms for m in rows]),
        }
    return out
