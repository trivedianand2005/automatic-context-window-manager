"""Shared business logic used by both the Streamlit UI and the FastAPI backend."""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, Field

from app.analysis.task_analyzer import analyze_task, analyze_task_with_llm, query_terms
from app.context.budget_optimizer import BudgetOptimizer, OptimizerOptions
from app.context.context_builder import assemble_package
from app.context.context_exporter import ExportFormat, export
from app.context.package_models import (
    ContextItem,
    ContextPackage,
    RepositorySummary,
    ResearchFinding,
    RetrievalConfig,
)
from app.context.summarizer import llm_summary, python_outline
from app.context.token_counter import get_token_counter, plan_budget
from app.core.config import BENCHMARK_FILE, RankingWeights, Settings, get_settings
from app.core.exceptions import BudgetExceededError, InvalidRepositoryError, PathSecurityError
from app.core.logging_config import get_logger
from app.core.models import Candidate, ScoreBreakdown
from app.evaluation import benchmark, metrics
from app.evaluation.baseline import rank_order_select
from app.evaluation.benchmark import MODES, BenchmarkTask, load_benchmark
from app.graph.dependency_graph import build_dependency_graph
from app.ingestion.repository_scanner import scan_repository
from app.integrations.llm_provider import get_llm_provider
from app.integrations.tinyfish_client import get_research_provider, provider_status
from app.parsing.import_resolver import resolve_all
from app.parsing.python_parser import parse_python
from app.retrieval.hybrid_ranker import rank_candidates
from app.retrieval.lexical_search import LexicalIndex
from app.retrieval.semantic_search import SemanticSearcher, semantic_dependencies_installed
from app.services.options import MODE_LABELS, BuildOptions, RetrievalMode
from app.storage.index_store import IndexedRepository, IndexStore
from app.storage.session_store import RunRecord, SessionStore
from app.utils.file_hashing import fingerprint, repository_id_for
from app.utils.security import safe_join, validate_repository_path

log = get_logger("service")
DEPENDENCY_MODE_WEIGHTS = RankingWeights(
    lexical=0.6, filename=0, symbol=0, dependency=0.4, test=0, config=0, semantic=0
)
MAX_LLM_SUMMARIES = 3


class MethodResult(BaseModel):
    mode: RetrievalMode
    label: str
    selected: list[str]
    kinds: dict[str, str]
    rendered_tokens: int
    usable_tokens: int
    utilization: float
    budget_violation: bool
    latency_ms: float
    precision_at_k: float | None = None
    recall_at_k: float | None = None
    mrr: float | None = None
    coverage: float | None = None
    full_coverage: float | None = None
    missing_relevant: list[str] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    task: str
    k: int
    relevant_paths: list[str]
    methods: list[MethodResult]
    notes: list[str] = Field(default_factory=list)


class BenchmarkReport(BaseModel):
    repository: str
    token_budget: int
    k: int
    tasks: list[ComparisonResult]
    aggregate: dict[str, dict[str, float | None]]
    tokenizer: str
    notes: list[str] = Field(default_factory=list)


def _ranked_selected(package: ContextPackage) -> list[str]:
    return [i.path for i in sorted(package.items, key=lambda i: (-i.combined_score, i.path))]


class ACWMService:
    def __init__(
        self,
        settings: Settings | None = None,
        store: IndexStore | None = None,
        sessions: SessionStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or IndexStore()
        self.sessions = sessions or SessionStore()
        self._semantic: SemanticSearcher | None = None
        self._last_research_status = "not used"

    # ------------------------------------------------------------------ status
    def provider_statuses(self) -> dict[str, str]:
        llm = get_llm_provider(
            self.settings.llm_provider, self.settings.llm_model, self.settings.llm_timeout_seconds
        )
        return {
            "llm": llm.status,
            "semantic": "available (sentence-transformers installed)"
            if semantic_dependencies_installed()
            else "unavailable (sentence-transformers not installed)",
            "tinyfish": provider_status(self.settings.tinyfish_enabled),
            "tinyfish_last_call": self._last_research_status,
        }

    # ---------------------------------------------------------------- indexing
    def index_repository(self, path: str | Path) -> IndexedRepository:
        root = validate_repository_path(path, self.settings.allowed_roots)
        if not root.exists():
            raise InvalidRepositoryError("Repository path does not exist.")
        if not root.is_dir():
            raise InvalidRepositoryError("Repository path is not a directory.")
        scan = scan_repository(root, self.settings)
        files = {f.path: f for f in scan.files}
        modules = {}
        for f in scan.files:
            if f.language == "python":
                info = parse_python(f.path, f.content)
                modules[f.path] = info
                if info.parse_error:
                    scan.report.parse_warnings.append(f"{f.path}: {info.parse_error}")
        resolved = resolve_all(list(modules.values()))
        unresolved = [r for r in resolved if r.status == "unresolved"]
        for r in unresolved[:50]:
            scan.report.parse_warnings.append(
                f"{r.source_path}:{r.line} unresolved import `{r.raw}` ({r.note})"
            )
        graph = build_dependency_graph(scan.files, list(modules.values()), resolved)
        repo = IndexedRepository(
            repository_id=repository_id_for(str(root)),
            root=root,
            fingerprint=fingerprint((f.path, f.sha256) for f in scan.files),
            files=files,
            modules=modules,
            resolved_imports=resolved,
            graph=graph,
            lexical=LexicalIndex(scan.files, modules),
            report=scan.report,
            encoding=self.settings.tokenizer_encoding,
            created_at=time.time(),
        )
        if not files:
            repo.warnings.append("Repository contains no indexable files.")
        self.store.put(repo)
        log.info("Indexed %s files (%s tokens)", len(files), scan.report.total_tokens)
        return repo

    def repository_summary(self, repo: IndexedRepository) -> RepositorySummary:
        return RepositorySummary(
            repository_id=repo.repository_id,
            root_name=repo.root.name,
            fingerprint=repo.fingerprint,
            indexed_files=len(repo.files),
            languages=repo.report.languages,
            file_types=repo.report.file_types,
            total_tokens=repo.report.total_tokens,
            module_count=len(repo.modules),
            symbol_count=repo.symbol_count,
            dependency_edges=sum(
                1 for u, v in repo.graph.edges if u.startswith("file:") and v.startswith("file:")
            ),
        )

    # ----------------------------------------------------------- build context
    def _validate_required(self, repo: IndexedRepository, paths: list[str]) -> list[str]:
        clean = []
        for p in paths:
            safe_join(repo.root, p)  # raises PathSecurityError on traversal
            norm = p.replace("\\", "/").removeprefix("./")
            if norm not in repo.files:
                raise PathSecurityError(f"Required path '{p}' is not an indexed file.")
            clean.append(norm)
        return clean

    def build_context(self, repository_id: str, opts: BuildOptions) -> ContextPackage:
        started = time.perf_counter()
        repo = self.store.get(repository_id)
        s = self.settings
        counter = get_token_counter(repo.encoding)
        warnings = list(counter.warnings)
        warnings += repo.warnings
        if repo.report.parse_warnings:
            warnings.append(
                f"{len(repo.report.parse_warnings)} indexing/parsing warnings (see indexing report)."
            )

        budget = s.budget.model_copy(
            update={
                k: v
                for k, v in {
                    "total_tokens": opts.token_budget,
                    "reserved_response_tokens": opts.reserved_response_tokens,
                }.items()
                if v is not None
            }
        )
        weights = opts.weights or s.weights
        depth = s.expansion_depth if opts.expansion_depth is None else opts.expansion_depth
        required = self._validate_required(repo, opts.required_paths)

        llm = None
        if opts.use_llm_analysis or opts.compression == "llm":
            llm = get_llm_provider(s.llm_provider, s.llm_model, s.llm_timeout_seconds)
            if not llm.available:
                warnings.append(f"LLM requested but {llm.status}; deterministic fallback used.")
        analysis = (
            analyze_task_with_llm(opts.task, llm)
            if opts.use_llm_analysis
            else analyze_task(opts.task)
        )
        warnings += analysis.notes
        primary, secondary = query_terms(analysis)
        plan = plan_budget(budget, opts.task, counter)
        if plan.usable_tokens <= 0:
            raise BudgetExceededError(
                "Token budget is too small after reserving system, task, response and safety "
                "margin tokens.",
                details=plan.model_dump(),
            )
        hits = repo.lexical.search(primary, secondary)

        semantic_scores = None
        semantic_status = "disabled"
        if opts.use_semantic:
            if self._semantic is None:
                self._semantic = SemanticSearcher()
            if self._semantic.available:
                semantic_scores = self._semantic.score(
                    opts.task, {p: f.content for p, f in repo.files.items()}
                )
            semantic_status = (
                "enabled" if semantic_scores else f"unavailable: {self._semantic.reason}"
            )
            if not semantic_scores:
                warnings.append(
                    f"Semantic search requested but {self._semantic.reason}; BM25/graph only."
                )

        extra_items: list[ContextItem] = []
        if opts.mode == "baseline":
            max_bm25 = max((h.score for h in hits), default=0.0) or 1.0
            candidates = [
                Candidate(
                    path=h.path,
                    file_type=repo.files[h.path].file_type,
                    language=repo.files[h.path].language,
                    tokens=repo.files[h.path].tokens,
                    raw_bm25=h.score,
                    scores=ScoreBreakdown(lexical=round(h.score / max_bm25, 4)),
                    combined=round(h.score / max_bm25, 6),
                    matched_terms=h.matched_terms,
                    matched_symbols=h.matched_symbols,
                    reasons=[f"BM25 match on {', '.join(h.matched_terms[:6])}"],
                )
                for h in hits
            ]
            result = rank_order_select(candidates, repo.files, plan, counter)
            if required:
                warnings.append("Required paths are only honoured in 'acwm' mode.")
            weights_used = {"lexical": 1.0}
            compression = "none"
        elif opts.mode == "dependency":
            candidates, _ = rank_candidates(
                list(repo.files.values()),
                repo.modules,
                repo.graph,
                hits,
                analysis,
                primary,
                secondary,
                DEPENDENCY_MODE_WEIGHTS,
                depth,
            )
            result = rank_order_select(candidates, repo.files, plan, counter)
            if required:
                warnings.append("Required paths are only honoured in 'acwm' mode.")
            weights_used = {"lexical": 0.6, "dependency": 0.4}
            compression = "none"
        else:
            candidates, _ = rank_candidates(
                list(repo.files.values()),
                repo.modules,
                repo.graph,
                hits,
                analysis,
                primary,
                secondary,
                weights,
                depth,
                semantic_scores=semantic_scores,
            )
            optimizer = BudgetOptimizer(
                repo.files,
                repo.modules,
                repo.graph,
                counter,
                plan,
                set(primary + secondary),
                OptimizerOptions(
                    redundancy_penalty=opts.redundancy_penalty,
                    allow_excerpts=opts.compression != "none",
                ),
            )
            result = optimizer.optimize(candidates, required)
            weights_used = {
                k: v
                for k, v in weights.model_dump().items()
                if not (k == "semantic" and not semantic_scores)
            }
            compression = opts.compression
            if opts.compression == "llm":
                extra_items = self._llm_summaries(repo, opts, result, plan, counter, llm, warnings)

        if not candidates:
            warnings.append("No candidate files matched the task terms.")

        research: list[ResearchFinding] = []
        if opts.include_research:
            research = self._research(opts.task, primary + secondary, warnings)

        cfg = RetrievalConfig(
            mode=MODE_LABELS[opts.mode],
            weights=weights_used,
            expansion_depth=depth,
            compression=compression,
            semantic=semantic_status,
            llm=llm.status if llm else "not used",
            analyzer=analysis.analyzer,
            required_paths=required,
        )
        package = assemble_package(
            task=opts.task,
            analysis=analysis,
            repository=self.repository_summary(repo),
            configuration=cfg,
            result=result,
            candidates=candidates,
            files=repo.files,
            graph=repo.graph,
            plan=plan,
            counter=counter,
            warnings=list(dict.fromkeys(warnings)),
            extra_items=extra_items,
            research=research,
        )
        package.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        self.sessions.record(
            RunRecord(
                timestamp=time.time(),
                repository_id=repository_id,
                task=opts.task[:200],
                mode=opts.mode,
                selected_files=len(package.items),
                rendered_tokens=package.token_stats.rendered_context_tokens,
                usable_tokens=plan.usable_tokens,
                latency_ms=package.latency_ms,
            )
        )
        return package

    def _llm_summaries(self, repo, opts, result, plan, counter, llm, warnings) -> list[ContextItem]:
        """Mode B: summaries for high-ranked files that did not fit; outline fallback."""
        items: list[ContextItem] = []
        remaining = plan.usable_tokens - result.used_tokens
        skipped = [(c, r) for c, r in result.excluded if r.startswith("does not fit")]
        for cand, _ in skipped[:MAX_LLM_SUMMARIES]:
            f = repo.files[cand.path]
            ex = llm_summary(f, opts.task, llm, counter) if llm and llm.available else None
            note = "LLM-generated summary (labelled; original file remains indexed)"
            if ex is None:
                info = repo.modules.get(cand.path)
                if info is None or not info.symbols:
                    continue
                ex = python_outline(f, info)
                note = "extractive outline (LLM summarization unavailable or failed)"
            cost = counter.count(ex.content) + plan.per_item_overhead_tokens
            if cost > remaining:
                continue
            remaining -= cost
            result.excluded = [(c, r) for c, r in result.excluded if c.path != cand.path]
            items.append(
                ContextItem(
                    path=cand.path,
                    kind=ex.kind,
                    is_partial=True,
                    language=f.language,
                    file_type=f.file_type,
                    line_ranges=ex.line_ranges,
                    total_lines=f.line_count,
                    tokens=cost,
                    full_file_tokens=f.tokens,
                    combined_score=cand.combined,
                    scores=cand.scores,
                    reasons=cand.reasons,
                    selection_note=note,
                    dependency_path=cand.dependency_path,
                    content=ex.content,
                )
            )
        if items and all(i.kind == "outline" for i in items):
            warnings.append("LLM summarization unavailable; extractive outlines used instead.")
        return items

    def _research(self, task: str, terms: list[str], warnings: list[str]) -> list[ResearchFinding]:
        provider = get_research_provider(
            True, self.settings.tinyfish_include_domains, self.settings.tinyfish_timeout_seconds
        )
        if provider is None:
            return []
        res = provider.research(task, terms)
        self._last_research_status = res.status
        if res.error:
            warnings.append(f"Documentation research failed: {res.error}")
        if res.provider == "mock":
            warnings.append("Documentation findings come from the offline MOCK provider.")
        return [
            ResearchFinding(
                title=f.title,
                url=f.url,
                snippet=f.snippet,
                source=f.source,
                provider_status=res.status,
            )
            for f in res.findings
        ]

    # --------------------------------------------------------------- compare
    def compare(
        self,
        repository_id: str,
        opts: BuildOptions,
        relevant_paths: list[str] | None = None,
        k: int = 5,
    ) -> ComparisonResult:
        relevant = set(relevant_paths or [])
        methods: list[MethodResult] = []
        packages: dict[str, ContextPackage] = {}
        for mode in ("baseline", "dependency", "acwm"):
            pkg = self.build_context(repository_id, opts.model_copy(update={"mode": mode}))
            packages[mode] = pkg
            ranked = _ranked_selected(pkg)
            selected = set(ranked)
            full = {i.path for i in pkg.items if i.kind == "full"}
            st = pkg.token_stats
            methods.append(
                MethodResult(
                    mode=mode,
                    label=MODE_LABELS[mode],
                    selected=ranked,
                    kinds={i.path: i.kind for i in pkg.items},
                    rendered_tokens=st.rendered_context_tokens,
                    usable_tokens=st.usable_tokens,
                    utilization=st.utilization,
                    budget_violation=st.rendered_context_tokens > st.usable_tokens,
                    latency_ms=pkg.latency_ms,
                    precision_at_k=metrics.precision_at_k(ranked, relevant, k)
                    if relevant
                    else None,
                    recall_at_k=metrics.recall_at_k(ranked, relevant, k),
                    mrr=metrics.reciprocal_rank(ranked, relevant) if relevant else None,
                    coverage=metrics.coverage(selected, relevant),
                    full_coverage=metrics.coverage(full, relevant),
                    missing_relevant=sorted(relevant - selected),
                )
            )
        notes = []
        if not relevant:
            notes.append("No ground-truth labels supplied: precision/recall/MRR/coverage are N/A.")
        base_tokens = packages["baseline"].token_stats.rendered_context_tokens
        if base_tokens:
            acwm_tokens = packages["acwm"].token_stats.rendered_context_tokens
            for pkg in packages.values():
                pkg.token_stats.reduction_vs_baseline = round(
                    1 - pkg.token_stats.rendered_context_tokens / base_tokens, 4
                )
            notes.append(
                f"ACWM rendered {acwm_tokens} tokens vs baseline {base_tokens} "
                f"({(1 - acwm_tokens / base_tokens) * 100:.1f}% difference; measured)."
            )
        return ComparisonResult(
            task=opts.task, k=k, relevant_paths=sorted(relevant), methods=methods, notes=notes
        )

    # ------------------------------------------------------------- benchmark
    @staticmethod
    def load_benchmark(path: Path = BENCHMARK_FILE) -> tuple[str, list[BenchmarkTask]]:
        return load_benchmark(path)

    def run_benchmarks(
        self, token_budget: int = 6000, k: int = 5, path: Path = BENCHMARK_FILE
    ) -> BenchmarkReport:
        from app.core.config import PROJECT_ROOT

        repo_rel, tasks = self.load_benchmark(path)
        repo = self.index_repository(PROJECT_ROOT / repo_rel)
        results = []
        for t in tasks:
            opts = BuildOptions(task=t.task, token_budget=token_budget)
            results.append(self.compare(repo.repository_id, opts, t.relevant, k=k))
        rows = {mode: [m for r in results for m in r.methods if m.mode == mode] for mode in MODES}
        aggregate = benchmark.aggregate(rows, k)
        counter = get_token_counter(repo.encoding)
        return BenchmarkReport(
            repository=repo_rel,
            token_budget=token_budget,
            k=k,
            tasks=results,
            aggregate=aggregate,
            tokenizer=f"{counter.method}:{counter.encoding_name}",
            notes=[
                "All numbers are measured on the bundled sample repository at run time.",
                "Latency includes ranking and packaging, excluding indexing.",
            ],
        )

    # ---------------------------------------------------------------- export
    @staticmethod
    def export(package: ContextPackage, fmt: ExportFormat) -> str:
        return export(package, fmt)
