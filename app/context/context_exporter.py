"""Export context packages to Markdown, JSON (schema-validated) and plain text."""

from __future__ import annotations

import json
from typing import Literal

from app.context.context_builder import fence_for, item_header, render_item
from app.context.package_models import ContextPackage

ExportFormat = Literal["markdown", "json", "txt"]
MIME_TYPES = {"markdown": "text/markdown", "json": "application/json", "txt": "text/plain"}
EXTENSIONS = {"markdown": "md", "json": "json", "txt": "txt"}


def package_json_schema() -> dict:
    return ContextPackage.model_json_schema()


def to_json(package: ContextPackage) -> str:
    text = package.model_dump_json(indent=2)
    # Round-trip validation against the schema-defining model.
    ContextPackage.model_validate_json(text)
    return text


def validate_package_json(text: str) -> ContextPackage:
    return ContextPackage.model_validate_json(text)


def _stats_lines(p: ContextPackage) -> list[str]:
    s = p.token_stats
    pct = lambda v: "N/A" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    return [
        f"- Tokenizer: `{s.tokenizer}` (estimate; not the target model's authoritative count)",
        f"- Total budget: {s.total_budget} | reserved: system {s.reserved_system_tokens}, "
        f"task {s.reserved_task_tokens}, response {s.reserved_response_tokens}, "
        f"safety margin {s.safety_margin_tokens}",
        f"- Usable context budget: {s.usable_tokens}",
        f"- Rendered context: {s.rendered_context_tokens} tokens "
        f"(utilization {pct(s.utilization)}, remaining {s.remaining_tokens})",
        f"- Indexed repository: {s.total_indexed_tokens} tokens; candidates: {s.candidate_tokens}",
        f"- Reduction vs full repository: {pct(s.reduction_vs_full_repository)}; "
        f"vs baseline: {pct(s.reduction_vs_baseline)}",
    ]


def to_markdown(p: ContextPackage, include_explanations: bool = True) -> str:
    out = [f"# ACWM Context Package (schema {p.schema_version})", "", "## Task", "", p.task, ""]
    r = p.repository
    out += [
        "## Repository summary",
        "",
        f"- Root: `{r.root_name}` (id `{r.repository_id}`, fingerprint `{r.fingerprint}`)",
        f"- Indexed files: {r.indexed_files}; modules: {r.module_count}; symbols: "
        f"{r.symbol_count}; dependency edges: {r.dependency_edges}",
        f"- Languages: {', '.join(f'{k} ({v})' for k, v in r.languages.items())}",
        "",
    ]
    c = p.configuration
    out += [
        "## Retrieval configuration",
        "",
        f"- Mode: {c.mode}; compression: {c.compression}; expansion depth: {c.expansion_depth}",
        f"- Analyzer: {c.analyzer}; semantic: {c.semantic}; LLM: {c.llm}",
        f"- Weights: {', '.join(f'{k}={v}' for k, v in c.weights.items())}",
        "",
        "## Token statistics",
        "",
        *_stats_lines(p),
        "",
    ]
    if include_explanations:
        out += [
            "## Selected files and why",
            "",
            "| # | Path | Kind | Tokens | Score | Reasons |",
            "|---|---|---|---|---|---|",
        ]
        for n, item in enumerate(p.items, 1):
            reasons = "; ".join(item.reasons[:3] + [item.selection_note]).replace("|", "\\|")
            out.append(
                f"| {n} | `{item.path}` | {item.kind}{' (partial)' if item.is_partial else ''} | "
                f"{item.tokens} | {item.combined_score:.3f} | {reasons} |"
            )
        out.append("")
        if p.dependencies:
            out += ["## Dependencies among selected files", ""]
            out += [
                f"- `{d.source}` -> `{d.target}` ({d.relation}, {d.confidence})"
                for d in p.dependencies
            ]
            out.append("")
        out += ["## Relevant tests", ""] + ([f"- `{t}`" for t in p.tests] or ["- none selected"])
        out += ["", "## Relevant configuration", ""]
        out += [f"- `{t}`" for t in p.config_files] or ["- none selected"]
        out.append("")
    out += ["## Code context", ""]
    out += [render_item(item) for item in p.items]
    if p.research_findings:
        out += ["## External documentation findings (untrusted, verify before use)", ""]
        for f in p.research_findings:
            out.append(f"- [{f.title}]({f.url}) ({f.source}, {f.provider_status}): {f.snippet}")
        out.append("")
    if include_explanations and p.excluded:
        out += [
            "## Excluded candidates",
            "",
            "| Path | Tokens | Score | Reason |",
            "|---|---|---|---|",
        ]
        out += [
            f"| `{e.path}` | {e.tokens} | {e.combined_score:.3f} | {e.reason} |"
            for e in p.excluded[:40]
        ]
        out.append("")
    out += ["## Known omissions", ""] + ([f"- {o}" for o in p.omissions] or ["- none recorded"])
    out += ["", "## Warnings", ""] + ([f"- {w}" for w in p.warnings] or ["- none"])
    out += ["", "## Limitations", "", p.disclaimer, ""]
    return "\n".join(out)


def to_text(p: ContextPackage) -> str:
    """Compact, agent-facing plain text: task, selected code, omissions."""
    out = [
        "TASK:",
        p.task,
        "",
        f"CONTEXT ({len(p.items)} items, "
        f"~{p.token_stats.rendered_context_tokens} tokens, {p.token_stats.tokenizer}):",
        "",
    ]
    for item in p.items:
        fence = fence_for(item.content)
        out += [item_header(item).lstrip("# "), fence, item.content, fence, ""]
    if p.research_findings:
        out.append("EXTERNAL FINDINGS (untrusted):")
        out += [f"- {f.title} <{f.url}>: {f.snippet}" for f in p.research_findings]
        out.append("")
    out += ["KNOWN OMISSIONS:"] + [f"- {o}" for o in p.omissions or ["none recorded"]]
    out += ["", "WARNINGS:"] + [f"- {w}" for w in p.warnings or ["none"]]
    out += ["", "NOTE: " + p.disclaimer]
    return "\n".join(out)


def export(p: ContextPackage, fmt: ExportFormat) -> str:
    if fmt == "markdown":
        return to_markdown(p)
    if fmt == "json":
        return to_json(p)
    if fmt == "txt":
        return to_text(p)
    raise ValueError(f"Unsupported export format: {fmt}")


def schema_text() -> str:
    return json.dumps(package_json_schema(), indent=2)
