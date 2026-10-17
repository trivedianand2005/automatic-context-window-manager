"""One-command ACWM demo (no API keys, network or database required).

    python scripts/run_demo.py [--budget 4000] [--task "..."] [--out demo_output]

Steps: index the sample FastAPI repository -> analyse the task -> BM25 retrieval ->
dependency graph expansion -> budget optimization -> context package -> baseline
comparison -> Markdown/JSON export -> metrics and warnings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import SAMPLE_REPO_PATH  # noqa: E402
from app.services.acwm_service import ACWMService  # noqa: E402
from app.services.options import BuildOptions  # noqa: E402

DEFAULT_TASK = (
    "Add JWT authentication to the FastAPI application and create tests for protected routes."
)


def fmt(v: float | None) -> str:
    return "N/A" if v is None else f"{v:.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--out", default=str(ROOT / "demo_output"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    service = ACWMService()

    print("=" * 78)
    print("ACWM demo  |  task:", args.task)
    print("=" * 78)
    repo = service.index_repository(SAMPLE_REPO_PATH)
    rep = repo.report
    print(
        f"\n[1] Indexed {rep.indexed}/{rep.total_discovered} files from {repo.root.name} "
        f"({rep.total_tokens} est. tokens, tokenizer {rep.tokenizer}, {rep.duration_ms} ms)"
    )
    print(f"    languages={rep.languages} types={rep.file_types} excluded={len(rep.excluded)}")
    file_edges = [
        (u, v, d)
        for u, v, d in repo.graph.edges(data=True)
        if u.startswith("file:") and v.startswith("file:")
    ]
    print(
        f"[2] Parsed {len(repo.modules)} Python modules, {repo.symbol_count} symbols; "
        f"dependency graph has {len(file_edges)} file-level edges"
    )

    pkg = service.build_context(
        repo.repository_id, BuildOptions(task=args.task, token_budget=args.budget)
    )
    a = pkg.analysis
    print(f"[3] Task analysis: keywords={a.keywords} wants_tests={a.wants_tests}")
    st = pkg.token_stats
    print(
        f"[4] Budget: total {st.total_budget}, reserved "
        f"{st.total_budget - st.usable_tokens}, usable {st.usable_tokens}"
    )
    print(
        f"[5] ACWM selected {len(pkg.items)} items, {st.rendered_context_tokens} tokens "
        f"(utilization {st.utilization:.0%}, {st.reduction_vs_full_repository:.0%} smaller "
        f"than the whole repository):"
    )
    for item in pkg.items:
        part = " PARTIAL" if item.is_partial else ""
        print(
            f"    - {item.path:<38} {item.kind}{part:<8} {item.tokens:>5} tok  "
            f"score {item.combined_score:.3f}"
        )
        if item.dependency_path:
            print(f"        via {' -> '.join(item.dependency_path)}")
    print(f"    excluded candidates: {len(pkg.excluded)}; omissions: {len(pkg.omissions)}")

    _, tasks = service.load_benchmark()
    labels = next((t.relevant for t in tasks if t.task == args.task), [])
    cmp = service.compare(
        repo.repository_id, BuildOptions(task=args.task, token_budget=args.budget), labels
    )
    print(
        f"\n[6] Comparison at the same usable budget ({st.usable_tokens} tokens)"
        + ("" if labels else " - no ground-truth labels for this task, metrics N/A")
    )
    print(
        f"    {'method':<11} {'files':>5} {'tokens':>7} {'P@5':>5} {'R@5':>5} {'MRR':>5} "
        f"{'cover':>6}  missing relevant"
    )
    for m in cmp.methods:
        print(
            f"    {m.mode:<11} {len(m.selected):>5} {m.rendered_tokens:>7} "
            f"{fmt(m.precision_at_k):>5} {fmt(m.recall_at_k):>5} {fmt(m.mrr):>5} "
            f"{fmt(m.coverage):>6}  {', '.join(p.split('/')[-1] for p in m.missing_relevant)}"
        )
    for n in cmp.notes:
        print("    note:", n)

    md = out / "context_package.md"
    js = out / "context_package.json"
    md.write_text(service.export(pkg, "markdown"), encoding="utf-8")
    js.write_text(service.export(pkg, "json"), encoding="utf-8")
    (out / "context_package.txt").write_text(service.export(pkg, "txt"), encoding="utf-8")
    print(f"\n[7] Exported: {md}\n              {js}\n              {out / 'context_package.txt'}")
    print("\n[8] Warnings:")
    for w in pkg.warnings:
        print("    -", w)
    print("    Known omissions:")
    for o in pkg.omissions[:8]:
        print("    -", o)
    print("\nDone. These numbers were measured just now on the bundled sample repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
