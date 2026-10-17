"""Reproducible benchmark: baseline vs dependency expansion vs full ACWM.

    python scripts/evaluate_benchmarks.py [--budgets 3000 4000 6000] [--k 5] [--out demo_output]

Writes demo_output/benchmark_results.json and prints a Markdown table per budget.
All numbers are measured at run time; latency varies by machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.acwm_service import ACWMService  # noqa: E402

COLUMNS = [
    "precision@{k}",
    "recall@{k}",
    "mrr",
    "coverage",
    "full_coverage",
    "mean_rendered_tokens",
    "mean_utilization",
    "budget_violations",
    "mean_latency_ms",
]


def cell(v: float | None) -> str:
    return "N/A" if v is None else f"{v:.3f}" if abs(v) < 100 else f"{v:.0f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budgets", type=int, nargs="+", default=[3000, 4000, 6000])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", default=str(ROOT / "demo_output"))
    args = parser.parse_args()
    service = ACWMService()
    results = []
    for budget in args.budgets:
        report = service.run_benchmarks(token_budget=budget, k=args.k)
        results.append(report.model_dump())
        cols = [c.format(k=args.k) for c in COLUMNS]
        usable = report.tasks[0].methods[0].usable_tokens if report.tasks else "N/A"
        print(
            f"\n### Total budget {budget} tokens (usable for context on task 1: {usable}; "
            f"{len(report.tasks)} tasks; {report.tokenizer})\n"
        )
        print("| method | " + " | ".join(cols) + " |")
        print("|---" * (len(cols) + 1) + "|")
        for mode, agg in report.aggregate.items():
            print(f"| {mode} | " + " | ".join(cell(agg[c]) for c in cols) + " |")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "benchmark_results.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
