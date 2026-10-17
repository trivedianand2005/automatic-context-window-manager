"""ACWM Streamlit UI.

Run with:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # allow `streamlit run app/streamlit_app.py` from the repo root
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402  (ships with streamlit)
import streamlit as st  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.context.context_exporter import EXTENSIONS, MIME_TYPES  # noqa: E402
from app.context.token_counter import SUPPORTED_ENCODINGS  # noqa: E402
from app.core.config import SAMPLE_REPO_PATH, RankingWeights, get_settings  # noqa: E402
from app.core.exceptions import ACWMError  # noqa: E402
from app.graph.dependency_graph import file_node, to_dot  # noqa: E402
from app.retrieval.semantic_search import semantic_dependencies_installed  # noqa: E402
from app.services.acwm_service import ACWMService  # noqa: E402
from app.services.options import MODE_LABELS, BuildOptions  # noqa: E402

st.set_page_config(page_title="ACWM - Automatic Context Window Manager", layout="wide")
EXAMPLE_TASK = (
    "Add JWT authentication to the FastAPI application and create tests for protected routes."
)


ss = st.session_state
# One service per browser session: settings, indexes and run history are never shared
# between visitors when the app is deployed publicly.
if "service" not in ss:
    ss.service = ACWMService(get_settings())
service: ACWMService = ss.service
ss.setdefault("repo_id", None)
ss.setdefault("package", None)
ss.setdefault("comparison", None)
ss.setdefault("benchmark", None)
ss.setdefault("task", EXAMPLE_TASK)
ss.setdefault("excluded_findings", set())


def current_repo():
    if not ss.repo_id:
        return None
    try:
        return service.store.get(ss.repo_id)
    except ACWMError:
        ss.repo_id = None
        return None


def show_error(exc: Exception) -> None:
    if isinstance(exc, ACWMError):
        st.error(f"{exc.message}")
        if exc.details:
            st.caption(str(exc.details))
    elif isinstance(exc, ValidationError):
        st.error("Invalid input: " + "; ".join(e["msg"] for e in exc.errors()))
    else:
        st.error(f"Unexpected error: {type(exc).__name__}: {exc}")


def pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v * 100:.1f}%"


repo = current_repo()

# ------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("ACWM")
    st.caption("Automatic Context Window Manager")
    if repo:
        st.success(
            f"Indexed: **{repo.root.name}**  \n{len(repo.files)} files, "
            f"{repo.report.total_tokens:,} tokens"
        )
    else:
        st.info("No repository indexed yet. Use **Repository Explorer**.")
    st.markdown("**Providers**")
    for name, status in service.provider_statuses().items():
        st.caption(f"{name}: {status}")

tabs = st.tabs(
    [
        "Dashboard",
        "Repository Explorer",
        "Context Builder",
        "Results",
        "Comparison",
        "Export",
        "Benchmarks",
        "Settings",
    ]
)

# ------------------------------------------------------------------ dashboard
with tabs[0]:
    st.header("Automatic Context Window Manager")
    st.write(
        "ACWM selects the repository files and symbols a coding agent needs for a task, under a "
        "token budget. It combines BM25 retrieval, AST symbol extraction, an import dependency "
        "graph and a budget optimizer, and explains every decision. It does not execute "
        "repository code and does not claim complete program understanding."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Indexing status", "indexed" if repo else "not indexed")
    c2.metric("Indexed files", len(repo.files) if repo else 0)
    c3.metric("Estimated tokens", f"{repo.report.total_tokens:,}" if repo else 0)
    c4.metric("Token budget", f"{service.settings.budget.total_tokens:,}")
    st.subheader("Recent task runs")
    runs = service.sessions.recent(10)
    if runs:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "task": r.task,
                        "mode": r.mode,
                        "files": r.selected_files,
                        "tokens": r.rendered_tokens,
                        "usable": r.usable_tokens,
                        "latency ms": r.latency_ms,
                    }
                    for r in runs
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("No runs yet in this session.")
    st.subheader("Quick start")
    st.markdown(
        "1. **Repository Explorer** -> index the sample repository.\n"
        "2. **Context Builder** -> enter a task and build.\n"
        "3. **Results**, **Comparison**, **Export** -> inspect, compare, download."
    )

# --------------------------------------------------------- repository explorer
with tabs[1]:
    st.header("Repository Explorer")
    roots = ", ".join(str(r) for r in service.settings.allowed_roots)
    st.caption(f"Allowed roots: {roots}. Set ACWM_ALLOWED_ROOTS to permit other directories.")
    path = st.text_input("Repository directory", value=str(SAMPLE_REPO_PATH))
    if st.button("Index / re-index repository", type="primary"):
        with st.spinner("Indexing..."):
            try:
                repo = service.index_repository(path)
                ss.repo_id = repo.repository_id
                ss.package = None
                st.success(f"Indexed {len(repo.files)} files in {repo.report.duration_ms} ms.")
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
    repo = current_repo()
    if repo:
        rep = repo.report
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Discovered", rep.total_discovered)
        c2.metric("Indexed", rep.indexed)
        c3.metric("Excluded", len(rep.excluded))
        c4.metric("Skipped (limits)", rep.skipped)
        c5.metric("Tokens", f"{rep.total_tokens:,}")
        st.caption(
            f"Tokenizer: {rep.tokenizer} (estimates). Languages: {rep.languages}. "
            f"File types: {rep.file_types}."
        )
        sub = st.tabs(["Files", "Symbols", "Dependencies", "Excluded", "Warnings"])
        with sub[0]:
            flt = st.text_input("Filter paths", key="file_filter")
            rows = [
                {
                    "path": f.path,
                    "type": f.file_type,
                    "language": f.language,
                    "lines": f.line_count,
                    "tokens": f.tokens,
                }
                for f in repo.files.values()
                if flt.lower() in f.path.lower()
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        with sub[1]:
            py_files = sorted(repo.modules)
            if py_files:
                sel = st.selectbox("Python module", py_files)
                info = repo.modules[sel]
                if info.parse_error:
                    st.warning(info.parse_error)
                st.caption(
                    f"Module `{info.module}`"
                    + (f" - {info.docstring.splitlines()[0]}" if info.docstring else "")
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "id": s.id,
                                "kind": s.kind,
                                "lines": f"{s.start_line}-{s.end_line}",
                                "signature": s.signature,
                                "docstring": (s.docstring or "").splitlines()[0]
                                if s.docstring
                                else "",
                            }
                            for s in info.symbols
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
                st.dataframe(
                    pd.DataFrame([i.model_dump() for i in info.imports]),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("No Python modules indexed.")
        with sub[2]:
            files = sorted(repo.files)
            if files:
                focus = st.selectbox("File", files, key="dep_focus")
                node = file_node(focus)
                out_rows = [
                    {
                        "target": repo.graph.nodes[v]["path"],
                        **{k: d[k] for k in ("relation", "confidence")},
                        "note": d.get("note", ""),
                    }
                    for _, v, d in repo.graph.out_edges(node, data=True)
                    if repo.graph.nodes[v].get("kind") == "file"
                ]
                in_rows = [
                    {
                        "source": repo.graph.nodes[u]["path"],
                        **{k: d[k] for k in ("relation", "confidence")},
                    }
                    for u, _, d in repo.graph.in_edges(node, data=True)
                    if repo.graph.nodes[u].get("kind") == "file"
                ]
                c1, c2 = st.columns(2)
                c1.markdown("**Depends on**")
                c1.dataframe(pd.DataFrame(out_rows), width="stretch", hide_index=True)
                c2.markdown("**Used by**")
                c2.dataframe(pd.DataFrame(in_rows), width="stretch", hide_index=True)
                st.graphviz_chart(to_dot(repo.graph, highlight={focus}))
                st.caption(
                    "Solid = high confidence, dashed = medium, dotted = low. Static "
                    "imports only; runtime wiring is not visible."
                )
        with sub[3]:
            st.dataframe(
                pd.DataFrame([e.model_dump() for e in rep.excluded]),
                width="stretch",
                hide_index=True,
            )
        with sub[4]:
            if rep.parse_warnings or repo.warnings:
                for w in repo.warnings + rep.parse_warnings:
                    st.warning(w)
            else:
                st.caption("No warnings.")

# ------------------------------------------------------------ context builder
with tabs[2]:
    st.header("Context Builder")
    repo = current_repo()
    if not repo:
        st.info("Index a repository first (Repository Explorer).")
    else:
        ss.task = st.text_area("Coding task", value=ss.task, height=90)
        c1, c2, c3 = st.columns(3)
        budget = c1.number_input(
            "Total token budget", 500, 2_000_000, service.settings.budget.total_tokens, step=500
        )
        mode = c2.selectbox(
            "Retrieval mode", list(MODE_LABELS), index=0, format_func=lambda m: MODE_LABELS[m]
        )
        depth = c3.slider("Dependency expansion depth", 0, 5, service.settings.expansion_depth)
        c1, c2, c3 = st.columns(3)
        compression = c1.radio(
            "Compression",
            ["extractive", "llm", "none"],
            help="'llm' uses the configured LLM provider; falls back to "
            "extractive outlines if unavailable.",
        )
        sem_ok = semantic_dependencies_installed()
        use_semantic = c2.toggle(
            "Semantic search",
            value=False,
            disabled=not sem_ok,
            help=None if sem_ok else "Unavailable: sentence-transformers is not installed.",
        )
        use_llm_analysis = c2.toggle("LLM task analysis", value=False)
        include_research = c3.toggle(
            "Documentation research (TinyFish)",
            value=service.settings.tinyfish_enabled,
            help="Uses the real TinyFish Search API if TINYFISH_API_KEY is set, "
            "otherwise the offline mock provider.",
        )
        required = c3.multiselect("Required files", sorted(repo.files))
        with st.expander("Ranking weights (normalised signals)"):
            w0 = service.settings.weights
            cols = st.columns(4)
            weights = {}
            for i, name in enumerate(RankingWeights.model_fields):
                weights[name] = cols[i % 4].slider(name, 0.0, 1.0, float(getattr(w0, name)), 0.05)
            redundancy = st.checkbox("Redundancy penalty", value=True)
        if st.button("Build Context", type="primary"):
            try:
                opts = BuildOptions(
                    task=ss.task,
                    mode=mode,
                    token_budget=int(budget),
                    weights=RankingWeights(**weights),
                    expansion_depth=depth,
                    compression=compression,
                    use_semantic=use_semantic,
                    use_llm_analysis=use_llm_analysis,
                    include_research=include_research,
                    redundancy_penalty=redundancy,
                    required_paths=required,
                )
                with st.spinner("Building context..."):
                    ss.package = service.build_context(repo.repository_id, opts)
                    ss.excluded_findings = set()
                st.success(
                    f"Built context with {len(ss.package.items)} items in "
                    f"{ss.package.latency_ms} ms. See the **Results** tab."
                )
            except Exception as exc:  # noqa: BLE001
                show_error(exc)

# --------------------------------------------------------------------- results
with tabs[3]:
    st.header("Results")
    pkg = ss.package
    if pkg is None:
        st.info("Build a context package first.")
    else:
        s = pkg.token_stats
        c = st.columns(6)
        c[0].metric("Usable budget", f"{s.usable_tokens:,}")
        c[1].metric("Selected (rendered)", f"{s.rendered_context_tokens:,}")
        c[2].metric("Remaining", f"{s.remaining_tokens:,}")
        c[3].metric("Utilization", pct(s.utilization))
        c[4].metric("Reserved", f"{s.total_budget - s.usable_tokens:,}")
        c[5].metric("Reduction vs repo", pct(s.reduction_vs_full_repository))
        st.caption(
            f"Indexed: {s.total_indexed_tokens:,} tokens; candidates: "
            f"{s.candidate_tokens:,}; tokenizer {s.tokenizer} (estimate - the target "
            f"model's tokenizer may differ). Mode: {pkg.configuration.mode}. "
            f"Latency {pkg.latency_ms} ms."
        )
        st.subheader("Selected context")
        sel_df = pd.DataFrame(
            [
                {
                    "path": i.path,
                    "kind": i.kind + (" (partial)" if i.is_partial else ""),
                    "tokens": i.tokens,
                    "full file tokens": i.full_file_tokens,
                    "score": round(i.combined_score, 3),
                    **{k: round(v, 2) for k, v in i.scores.model_dump().items()},
                    "why": "; ".join(i.reasons[:2]),
                    "selection": i.selection_note,
                }
                for i in pkg.items
            ]
        )
        st.dataframe(sel_df, width="stretch", hide_index=True)
        if not sel_df.empty:
            st.bar_chart(sel_df.set_index("path")["tokens"])
        st.subheader("Excluded candidates")
        st.dataframe(
            pd.DataFrame([e.model_dump() for e in pkg.excluded]), width="stretch", hide_index=True
        )
        st.subheader("Dependencies among selected files")
        repo = current_repo()
        if repo:
            st.graphviz_chart(to_dot(repo.graph, highlight={i.path for i in pkg.items}))
        if pkg.research_findings:
            st.subheader("Documentation findings (external, untrusted)")
            for idx, f in enumerate(pkg.research_findings):
                keep = st.checkbox(
                    f"Include: {f.title}",
                    value=idx not in ss.excluded_findings,
                    key=f"finding_{idx}",
                )
                if keep:
                    ss.excluded_findings.discard(idx)
                else:
                    ss.excluded_findings.add(idx)
                st.caption(f"{f.url} - {f.source} - {f.provider_status}\n\n{f.snippet}")
        st.subheader("Warnings and known omissions")
        for w in pkg.warnings:
            st.warning(w)
        for o in pkg.omissions:
            st.info(o)
        st.subheader("Source previews")
        for i in pkg.items:
            with st.expander(f"{i.path} [{i.kind}] - {i.tokens} tokens"):
                st.caption(" | ".join(i.reasons) + f" | {i.selection_note}")
                st.code(i.content, language="python" if i.language == "python" else None)

# ------------------------------------------------------------------ comparison
with tabs[4]:
    st.header("Baseline vs ACWM")
    repo = current_repo()
    if not repo:
        st.info("Index a repository first.")
    else:
        bench_repo, bench_tasks = service.load_benchmark()
        preset = st.selectbox(
            "Load a benchmark task (prefills ground-truth labels)",
            ["(custom)"] + [t.id for t in bench_tasks],
        )
        chosen = next((t for t in bench_tasks if t.id == preset), None)
        task = st.text_area("Task", value=chosen.task if chosen else ss.task, key="cmp_task")
        budget = st.number_input(
            "Total token budget (same for all methods)",
            500,
            2_000_000,
            4000,
            step=500,
            key="cmp_budget",
        )
        labels = st.multiselect(
            "Ground-truth relevant files (optional)",
            sorted(repo.files),
            default=[p for p in (chosen.relevant if chosen else []) if p in repo.files],
        )
        if chosen and not Path(repo.root).samefile(service.settings.allowed_roots[0] / bench_repo):
            st.warning(
                "Benchmark labels refer to the sample repository; the indexed repository "
                "differs, so metrics may be meaningless."
            )
        if st.button("Run comparison", type="primary"):
            try:
                with st.spinner("Running three methods..."):
                    ss.comparison = service.compare(
                        repo.repository_id,
                        BuildOptions(task=task, token_budget=int(budget)),
                        labels,
                    )
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
        cmp = ss.comparison
        if cmp:
            relevant = set(cmp.relevant_paths)
            cols = st.columns(3)
            for col, m in zip(cols, cmp.methods, strict=True):
                with col:
                    st.markdown(f"**{m.label}**")
                    st.caption(
                        f"{m.rendered_tokens:,} / {m.usable_tokens:,} tokens "
                        f"({pct(m.utilization)}), {m.latency_ms} ms"
                    )
                    for p in m.selected:
                        mark = "✅" if p in relevant else ("▫️" if relevant else "")
                        st.text(f"{mark} {p} [{m.kinds[p]}]")
                    if m.missing_relevant:
                        st.caption("Missing: " + ", ".join(m.missing_relevant))
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "method": m.mode,
                            f"precision@{cmp.k}": m.precision_at_k,
                            f"recall@{cmp.k}": m.recall_at_k,
                            "MRR": m.mrr,
                            "coverage": m.coverage,
                            "full-file coverage": m.full_coverage,
                            "tokens": m.rendered_tokens,
                            "utilization": m.utilization,
                            "budget violation": m.budget_violation,
                            "latency ms": m.latency_ms,
                        }
                        for m in cmp.methods
                    ]
                ).fillna("N/A"),
                width="stretch",
                hide_index=True,
            )
            for n in cmp.notes:
                st.caption(n)

# ---------------------------------------------------------------------- export
with tabs[5]:
    st.header("Export")
    pkg = ss.package
    if pkg is None:
        st.info("Build a context package first.")
    else:
        if ss.excluded_findings:
            pkg = pkg.model_copy(
                update={
                    "research_findings": [
                        f
                        for i, f in enumerate(pkg.research_findings)
                        if i not in ss.excluded_findings
                    ]
                }
            )
        fmt = st.radio("Format", ["markdown", "json", "txt"], horizontal=True)
        try:
            content = service.export(pkg, fmt)
            st.download_button(
                f"Download .{EXTENSIONS[fmt]}",
                content,
                file_name=f"acwm_context.{EXTENSIONS[fmt]}",
                mime=MIME_TYPES[fmt],
            )
            st.caption(
                f"{len(content):,} characters. JSON exports are validated against the "
                "ContextPackage schema."
            )
            st.code(content[:60_000], language={"json": "json", "markdown": "markdown"}.get(fmt))
        except Exception as exc:  # noqa: BLE001
            show_error(exc)

# ------------------------------------------------------------------ benchmarks
with tabs[6]:
    st.header("Benchmarks")
    st.caption(
        "Runs every labelled task in benchmarks/sample_fastapi_tasks.json against the "
        "sample repository with all three methods at the same budget. Numbers are "
        "measured now, on this machine."
    )
    b = st.number_input("Total token budget", 1000, 200_000, 4000, step=500, key="bench_budget")
    if st.button("Run benchmarks", type="primary"):
        try:
            with st.spinner("Running benchmarks..."):
                ss.benchmark = service.run_benchmarks(token_budget=int(b))
        except Exception as exc:  # noqa: BLE001
            show_error(exc)
    rep = ss.benchmark
    if rep:
        st.subheader(f"Aggregate (budget {rep.token_budget}, K={rep.k}, {rep.tokenizer})")
        st.dataframe(pd.DataFrame(rep.aggregate).T.round(3).fillna("N/A"), width="stretch")
        st.subheader("Per task")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "task": t.task[:60],
                        "method": m.mode,
                        "coverage": m.coverage,
                        f"P@{rep.k}": m.precision_at_k,
                        "MRR": m.mrr,
                        "tokens": m.rendered_tokens,
                        "missing": ", ".join(m.missing_relevant),
                    }
                    for t in rep.tasks
                    for m in t.methods
                ]
            ).fillna("N/A"),
            width="stretch",
            hide_index=True,
        )
        for n in rep.notes:
            st.caption(n)

# -------------------------------------------------------------------- settings
with tabs[7]:
    st.header("Settings")
    st.caption(
        "Applies to this running process. Re-index after changing the tokenizer or exclusion rules."
    )
    cur = service.settings
    with st.form("settings"):
        c1, c2 = st.columns(2)
        total = c1.number_input(
            "Default total token budget", 500, 2_000_000, cur.budget.total_tokens, step=500
        )
        resp = c1.number_input(
            "Reserved response tokens", 0, 200_000, cur.budget.reserved_response_tokens, step=100
        )
        sysr = c1.number_input(
            "Reserved system tokens", 0, 50_000, cur.budget.reserved_system_tokens, step=50
        )
        enc = c2.selectbox(
            "Tokenizer encoding",
            SUPPORTED_ENCODINGS,
            index=SUPPORTED_ENCODINGS.index(cur.tokenizer_encoding)
            if cur.tokenizer_encoding in SUPPORTED_ENCODINGS
            else 0,
        )
        depth = c2.slider("Default expansion depth", 0, 5, cur.expansion_depth)
        dirs = c2.text_input(
            "Extra excluded directories (comma-separated)", ", ".join(cur.extra_excluded_dirs)
        )
        globs = c2.text_input(
            "Extra excluded globs (comma-separated)", ", ".join(cur.extra_excluded_globs)
        )
        st.markdown("**Default ranking weights**")
        cols = st.columns(7)
        wts = {
            n: cols[i].number_input(n, 0.0, 10.0, float(getattr(cur.weights, n)), 0.05)
            for i, n in enumerate(RankingWeights.model_fields)
        }
        st.markdown("**Optional providers**")
        c1, c2 = st.columns(2)
        llm = c1.selectbox(
            "LLM provider",
            ["none", "anthropic"],
            index=1 if cur.llm_provider == "anthropic" else 0,
            help="Credentials come only from environment variables (ANTHROPIC_API_KEY).",
        )
        model = c1.text_input("LLM model", cur.llm_model)
        tf = c2.checkbox("Enable TinyFish documentation research", cur.tinyfish_enabled)
        domains = c2.text_input("TinyFish include_domains", ", ".join(cur.tinyfish_include_domains))
        if st.form_submit_button("Save settings"):
            try:
                split = lambda s: [x.strip() for x in s.split(",") if x.strip()]  # noqa: E731
                service.settings = cur.model_copy(
                    update={
                        "budget": cur.budget.model_copy(
                            update={
                                "total_tokens": int(total),
                                "reserved_response_tokens": int(resp),
                                "reserved_system_tokens": int(sysr),
                            }
                        ),
                        "tokenizer_encoding": enc,
                        "expansion_depth": depth,
                        "extra_excluded_dirs": split(dirs),
                        "extra_excluded_globs": split(globs),
                        "weights": RankingWeights(**wts),
                        "llm_provider": llm,
                        "llm_model": model,
                        "tinyfish_enabled": tf,
                        "tinyfish_include_domains": split(domains),
                    }
                )
                st.success("Settings saved. Re-index to apply tokenizer/exclusion changes.")
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
    st.markdown("**Provider status**")
    st.json(service.provider_statuses())
