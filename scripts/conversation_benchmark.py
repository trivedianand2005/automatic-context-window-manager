"""Conversation-manager benchmark: full context vs naive truncation vs ACWM.

    python scripts/conversation_benchmark.py --dry-run          # no API keys needed
    python scripts/conversation_benchmark.py                     # live, uses config.yaml
    python scripts/conversation_benchmark.py --budget 3000 --judge llm --out demo_output/conv

Writes results.json, summary.csv, turns.csv, answers.csv and three PNG charts
(tokens_per_turn.png, cost_comparison.png, recall_accuracy.png) to the output directory.
Charts need matplotlib (pip install -r requirements-optional.txt); without it the data
files are still written.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.context.token_counter import get_token_counter  # noqa: E402
from app.conversation.config import load_conversation_config  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging_config import configure_logging  # noqa: E402
from app.evaluation.conversation_benchmark import STRATEGIES, run_benchmark  # noqa: E402
from app.evaluation.conversation_dataset import build_dataset  # noqa: E402

LABELS = {"full": "No management", "truncation": "Naive truncation", "acwm": "ACWM + manager"}
COLORS = {"full": "#9aa0a6", "truncation": "#e8710a", "acwm": "#1a73e8"}


def write_csvs(results: dict, out: Path) -> None:
    summary = results["summary"]
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    rows = [
        {"strategy": name, **row, "total_cost_usd": row["main_cost_usd"] + row["manager_cost_usd"]}
        for name, turns in results["per_turn"].items()
        for row in turns
    ]
    if rows:
        with (out / "turns.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    answers = [
        {
            "strategy": name,
            **{k: v for k, v in a.items() if k != "expected_keywords"},
            "expected_keywords": "|".join(a["expected_keywords"]),
        }
        for name, items in results["answers"].items()
        for a in items
    ]
    if answers:
        with (out / "answers.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(answers[0]))
            writer.writeheader()
            writer.writerows(answers)


def write_charts(results: dict, out: Path) -> list[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError:
        print("matplotlib is not installed; skipping charts (pip install matplotlib).")
        return []
    plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False})
    summary = {s["strategy"]: s for s in results["summary"]}
    names = [n for n in STRATEGIES if n in summary]
    labels = [LABELS[n] for n in names]
    colors = [COLORS[n] for n in names]
    budget = results["budget_tokens"]
    paths = []

    fig, ax = plt.subplots(figsize=(11, 5.5))
    for n in names:
        turns = results["per_turn"][n]
        ax.plot(
            [t["turn"] for t in turns],
            [t["context_tokens"] for t in turns],
            label=LABELS[n],
            color=COLORS[n],
            # Full context matches truncation until it overflows; draw it on top, dashed.
            linewidth=3 if n == "full" else 2.2,
            linestyle=(0, (2, 2)) if n == "full" else "-",
            zorder=4 if n == "full" else 3,
        )
        if summary[n]["overflow_turn"]:
            ax.scatter(
                [summary[n]["overflow_turn"]],
                [budget],
                marker="x",
                s=120,
                color=COLORS[n],
                zorder=5,
            )
            ax.annotate(
                f"overflow (turn {summary[n]['overflow_turn']})",
                (summary[n]["overflow_turn"], budget),
                textcoords="offset points",
                xytext=(8, 8),
                color=COLORS[n],
            )
        compactions = [t["turn"] for t in turns if t.get("compaction") == "llm"]
        if compactions:
            ys = [t["context_tokens"] for t in turns if t.get("compaction") == "llm"]
            ax.scatter(
                compactions,
                ys,
                marker="v",
                s=50,
                color=COLORS[n],
                zorder=5,
                label=f"{LABELS[n]}: manager compaction",
            )
    ax.axhline(budget, color="#d93025", linestyle="--", linewidth=1.2, label="Token budget")
    ax.set_xlabel("Conversation turn")
    ax.set_ylabel("Tokens sent to the main model")
    ax.set_title("Context size per turn")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    paths.append(out / "tokens_per_turn.png")
    fig.savefig(paths[-1], dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5.5))
    main_cost = [summary[n]["main_cost_usd"] for n in names]
    manager_cost = [summary[n]["manager_cost_usd"] for n in names]
    ax.bar(labels, main_cost, color=colors)
    ax.bar(labels, manager_cost, bottom=main_cost, color="#34a853")
    for i, n in enumerate(names):
        total = summary[n]["total_cost_usd"]
        note = f"${total:.4f}"
        if summary[n]["overflow_turn"]:
            note += f"\n(stopped at turn {summary[n]['overflow_turn']})"
        ax.annotate(note, (i, total), ha="center", textcoords="offset points", xytext=(0, 6))
    ax.set_ylabel("Estimated cost (USD)")
    ax.set_title(f"Total cost over {results['turns']} turns")
    ax.legend(
        handles=[
            Patch(color="#5f6368", label="Main model (bar colour)"),
            Patch(color="#34a853", label="Manager model"),
        ],
        frameon=False,
        loc="upper left",
    )
    ax.set_ylim(0, max(s["total_cost_usd"] for s in summary.values()) * 1.3 or 1)
    fig.tight_layout()
    paths.append(out / "cost_comparison.png")
    fig.savefig(paths[-1], dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5.5))
    acc = [summary[n]["recall_accuracy"] * 100 for n in names]
    ax.bar(labels, acc, color=colors)
    for i, n in enumerate(names):
        s = summary[n]
        ax.annotate(
            f"{acc[i]:.0f}%\n({s['recall_correct']}/{s['recall_total']})",
            (i, acc[i]),
            ha="center",
            textcoords="offset points",
            xytext=(0, 6),
        )
    ax.set_ylim(0, 115)
    ax.set_ylabel("Recall questions answered correctly (%)")
    title = "Recall of facts planted early in the conversation"
    if results["mode"].startswith("dry-run"):
        title += "\n(dry run: fact retained in context)"
    ax.set_title(title)
    fig.tight_layout()
    paths.append(out / "recall_accuracy.png")
    fig.savefig(paths[-1], dpi=200)
    plt.close(fig)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="mock models, no API keys")
    parser.add_argument("--budget", type=int, help="token budget (default: config.yaml)")
    parser.add_argument("--judge", choices=["keyword", "llm"], help="grading (default: config)")
    parser.add_argument("--config", type=Path, help="config file (default: config.yaml)")
    parser.add_argument("--out", type=Path, help="output directory (default: config)")
    args = parser.parse_args()

    configure_logging()
    cfg = load_conversation_config(args.config)
    budget = args.budget or cfg.benchmark.budget_tokens
    out = args.out or ROOT / cfg.benchmark.output_dir
    out.mkdir(parents=True, exist_ok=True)
    counter = get_token_counter(get_settings().tokenizer_encoding)
    dataset = build_dataset()
    try:
        results = run_benchmark(
            cfg, dataset, counter, budget, args.dry_run, args.judge or cfg.benchmark.judge
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out / "dataset.json").write_text(
        json.dumps([t.model_dump() for t in dataset], indent=2), encoding="utf-8"
    )
    write_csvs(results, out)
    charts = write_charts(results, out)

    print(f"\n{results['mode']} | budget {budget} tokens | {results['turns']} turns\n")
    print("| Strategy | Turns | Total tokens | Manager tokens | Cost (USD) | Recall |")
    print("|---|---|---|---|---|---|")
    for s in results["summary"]:
        turns = f"{s['turns_completed']}" + (
            f" (overflow at {s['overflow_turn']})" if s["overflow_turn"] else ""
        )
        manager = s["manager_input_tokens"] + s["manager_output_tokens"]
        print(
            f"| {LABELS[s['strategy']]} | {turns} | {s['total_tokens']:,} | {manager:,} | "
            f"${s['total_cost_usd']:.4f} | {s['recall_correct']}/{s['recall_total']} |"
        )
    print(f"\nWrote results to {out}")
    for p in charts:
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
