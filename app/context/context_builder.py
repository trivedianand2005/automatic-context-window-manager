"""Assemble a validated ContextPackage from an optimization result."""

from __future__ import annotations

import networkx as nx

from app.context.budget_optimizer import OptimizationResult, Selection
from app.context.package_models import (
    ContextItem,
    ContextPackage,
    DependencyEdge,
    ExcludedCandidate,
    RepositorySummary,
    ResearchFinding,
    RetrievalConfig,
    TokenStats,
)
from app.context.token_counter import BudgetPlan, TokenCounter, budget_exceeded_details
from app.core.exceptions import BudgetExceededError
from app.core.models import Candidate, RepoFile, TaskAnalysis
from app.graph.dependency_graph import file_node

FENCE_LANG = {
    "python": "python",
    "json": "json",
    "yaml": "yaml",
    "toml": "toml",
    "markdown": "markdown",
    "ini": "ini",
}


def item_header(item: ContextItem) -> str:
    ranges = ", ".join(f"{a}-{b}" for a, b in item.line_ranges) or "n/a"
    partial = " PARTIAL" if item.is_partial else ""
    return f"### {item.path} [{item.kind}{partial}; lines {ranges} of {item.total_lines}]"


def fence_for(content: str) -> str:
    fence = "```"
    while fence in content:
        fence += "`"
    return fence


def render_item(item: ContextItem) -> str:
    fence = fence_for(item.content)
    lang = "" if item.kind == "summary" else FENCE_LANG.get(item.language, "")
    return f"{item_header(item)}\n{fence}{lang}\n{item.content}\n{fence}\n"


def render_context_block(items: list[ContextItem]) -> str:
    """The agent-facing code context (what the usable budget applies to)."""
    return "\n".join(render_item(i) for i in items)


def _to_item(sel: Selection, f: RepoFile) -> ContextItem:
    cand = sel.candidate
    return ContextItem(
        path=cand.path,
        kind=sel.kind,
        is_partial=sel.kind != "full",
        language=f.language,
        file_type=f.file_type,
        line_ranges=sel.line_ranges,
        total_lines=f.line_count,
        symbols=sel.symbols,
        tokens=sel.tokens,
        full_file_tokens=f.tokens,
        combined_score=cand.combined,
        scores=cand.scores,
        reasons=cand.reasons,
        selection_note=sel.note,
        required=sel.required,
        dependency_path=cand.dependency_path,
        content=sel.content,
    )


def _order_items(items: list[ContextItem]) -> list[ContextItem]:
    group = {"config": 0, "source": 1, "other": 1, "docs": 3, "test": 2}
    return sorted(
        items, key=lambda i: (not i.required, group.get(i.file_type, 1), -i.combined_score, i.path)
    )


def assemble_package(
    *,
    task: str,
    analysis: TaskAnalysis,
    repository: RepositorySummary,
    configuration: RetrievalConfig,
    result: OptimizationResult,
    candidates: list[Candidate],
    files: dict[str, RepoFile],
    graph: nx.DiGraph,
    plan: BudgetPlan,
    counter: TokenCounter,
    warnings: list[str],
    extra_items: list[ContextItem] | None = None,
    research: list[ResearchFinding] | None = None,
    latency_ms: float = 0.0,
) -> ContextPackage:
    items = [_to_item(s, files[s.candidate.path]) for s in result.selected]
    items.extend(extra_items or [])
    items = _order_items(items)
    omissions = list(result.omissions)

    # Final validation: re-render and count; trim lowest-value non-required items if the
    # rendered block (headers + fences) exceeds the usable budget.
    rendered = counter.count(render_context_block(items))
    while rendered > plan.usable_tokens:
        removable = [i for i in items if not i.required]
        if not removable:
            details = budget_exceeded_details(plan, rendered, "required_files")
            raise BudgetExceededError(
                f"Required context ({rendered:,} tokens) exceeds the usable budget "
                f"({plan.usable_tokens:,} tokens). Increase the budget to at least "
                f"{details['suggested_budget']:,} tokens or remove required files.",
                details={
                    **details,
                    "rendered_tokens": rendered,
                    "usable_tokens": plan.usable_tokens,
                },
            )
        victim = min(removable, key=lambda i: (i.combined_score / max(i.tokens, 1), i.path))
        items.remove(victim)
        omissions.append(
            f"{victim.path} removed during final validation (rendered package exceeded budget)."
        )
        rendered = counter.count(render_context_block(items))

    selected_paths = {i.path for i in items}
    deps: list[DependencyEdge] = []
    for u, v, d in graph.edges(data=True):
        if graph.nodes[u].get("kind") != "file" or graph.nodes[v].get("kind") != "file":
            continue
        su, sv = graph.nodes[u]["path"], graph.nodes[v]["path"]
        if su in selected_paths and sv in selected_paths:
            deps.append(
                DependencyEdge(
                    source=su, target=sv, relation=d["relation"], confidence=d["confidence"]
                )
            )
    deps.sort(key=lambda e: (e.source, e.target))

    # Known omissions: strongly-related neighbours of selected files that were left out.
    excluded_paths = {c.path for c, _ in result.excluded}
    for item in items:
        node = file_node(item.path)
        for _, v, d in graph.out_edges(node, data=True):
            target = graph.nodes[v].get("path")
            if (
                graph.nodes[v].get("kind") == "file"
                and d["relation"] == "imports"
                and target in excluded_paths
                and target not in selected_paths
            ):
                omissions.append(
                    f"{item.path} imports {target}, which was not included (budget/threshold)."
                )
    if any(i.is_partial for i in items):
        omissions.append("Some files are partial excerpts; omitted line ranges are marked inline.")

    selected_tokens = sum(i.tokens for i in items)
    candidate_tokens = sum(c.tokens for c in candidates)
    total_indexed = repository.total_tokens
    stats = TokenStats(
        tokenizer=f"{counter.method}:{counter.encoding_name}",
        exact_for_target_model=False,
        total_indexed_tokens=total_indexed,
        candidate_tokens=candidate_tokens,
        selected_tokens=selected_tokens,
        rendered_context_tokens=rendered,
        total_budget=plan.total_tokens,
        reserved_system_tokens=plan.reserved_system_tokens,
        reserved_task_tokens=plan.reserved_task_tokens,
        reserved_response_tokens=plan.reserved_response_tokens,
        safety_margin_tokens=plan.safety_margin_tokens,
        usable_tokens=plan.usable_tokens,
        remaining_tokens=plan.usable_tokens - rendered,
        utilization=round(rendered / plan.usable_tokens, 4) if plan.usable_tokens else 0.0,
        reduction_vs_full_repository=(
            round(1 - rendered / total_indexed, 4) if total_indexed else None
        ),
    )
    excluded = [
        ExcludedCandidate(path=c.path, tokens=c.tokens, combined_score=c.combined, reason=r)
        for c, r in result.excluded
        if c.path not in selected_paths
    ]
    return ContextPackage(
        task=task,
        analysis=analysis,
        repository=repository,
        configuration=configuration,
        items=items,
        dependencies=deps,
        tests=[i.path for i in items if i.file_type == "test"],
        config_files=[i.path for i in items if i.file_type == "config"],
        excluded=excluded,
        omissions=list(dict.fromkeys(omissions)),
        warnings=warnings,
        token_stats=stats,
        research_findings=research or [],
        latency_ms=latency_ms,
    )
