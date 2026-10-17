"""Hybrid ranking: combine normalised relevance signals into one score.

Every component is normalised to [0, 1] before weighting:

    combined = sum(w_i * s_i) / sum(w_i)        over *enabled* signals

    lexical     BM25 score / max BM25 score for this query
    filename    share of primary query terms found in the path (1.0 on exact name match)
    symbol      best matching symbol BM25 / global max (1.0 on exact symbol-name match)
    dependency  propagated relevance from graph expansion (see graph_expansion.py)
    test        test files: higher when the task asks for tests and the test is linked
                to a directly relevant module
    config      config files: higher when the task mentions configuration or the file
                is reachable from relevant code
    semantic    optional embedding similarity (weight ignored when unavailable)

Documented adjustment: documentation files (Markdown etc.) are multiplied by
DOCS_PRIOR (0.5) unless the task hints at documentation. Prose that mentions many
task words (changelogs, READMEs) otherwise dominates BM25 while rarely being the
code a change needs. Docs are also never used as graph-expansion seeds.

Token cost and redundancy are *not* part of this score; they are applied by the
budget optimizer during selection (relevance-per-token and overlap penalties).
"""

from __future__ import annotations

from pathlib import PurePosixPath

import networkx as nx

from app.analysis.text_processing import tokenize
from app.core.config import RankingWeights
from app.core.models import Candidate, ModuleInfo, RepoFile, ScoreBreakdown, TaskAnalysis
from app.graph.dependency_graph import file_node
from app.graph.graph_expansion import ExpansionHit, expand
from app.retrieval.lexical_search import LexicalHit

SEED_LIMIT = 6
SEED_MIN_DIRECT = 0.25
DOCS_PRIOR = 0.5
TEST_LINK_MIN = 0.35


def _direct_score(s: ScoreBreakdown) -> float:
    return 0.6 * s.lexical + 0.2 * s.filename + 0.2 * s.symbol


def _filename_score(
    path: str, primary: list[str], secondary: list[str], components: list[str]
) -> float:
    p = PurePosixPath(path)
    names = {p.name.lower(), p.stem.lower()}
    if any(c.lower() in names or c.lower() == path.lower() for c in components):
        return 1.0
    path_terms = set(tokenize(path.replace("/", " ")))
    if not primary and not secondary:
        return 0.0
    hits = len(path_terms & set(primary)) + 0.5 * len(path_terms & set(secondary))
    return min(1.0, hits / max(1, min(len(primary), 3)))


def rank_candidates(
    files: list[RepoFile],
    modules: dict[str, ModuleInfo],
    graph: nx.DiGraph,
    lexical_hits: list[LexicalHit],
    analysis: TaskAnalysis,
    primary: list[str],
    secondary: list[str],
    weights: RankingWeights,
    expansion_depth: int = 2,
    semantic_scores: dict[str, float] | None = None,
    use_dependency: bool = True,
) -> tuple[list[Candidate], dict[str, ExpansionHit]]:
    by_path = {f.path: f for f in files}
    hits = {h.path: h for h in lexical_hits}
    max_bm25 = max((h.score for h in lexical_hits), default=0.0) or 1.0
    max_sym = max((s for h in lexical_hits for s in h.symbol_scores.values()), default=0.0) or 1.0
    component_lower = {c.lower() for c in analysis.component_names}

    breakdowns: dict[str, ScoreBreakdown] = {}
    for f in files:
        hit = hits.get(f.path)
        s = ScoreBreakdown()
        if hit:
            s.lexical = hit.score / max_bm25
            s.symbol = max(hit.symbol_scores.values(), default=0.0) / max_sym
        s.filename = _filename_score(f.path, primary, secondary, analysis.component_names)
        info = modules.get(f.path)
        if (
            info
            and component_lower
            and any(sym.name.lower() in component_lower for sym in info.symbols)
        ):
            s.symbol = 1.0
        if semantic_scores:
            s.semantic = semantic_scores.get(f.path, 0.0)
        breakdowns[f.path] = s

    # Graph expansion from the strongest direct matches.
    expansion: dict[str, ExpansionHit] = {}
    if use_dependency and expansion_depth > 0:
        ranked_direct = sorted(
            (
                (p, _direct_score(s))
                for p, s in breakdowns.items()
                if by_path[p].file_type != "docs"
            ),
            key=lambda x: (-x[1], x[0]),
        )
        seeds = {p: sc for p, sc in ranked_direct[:SEED_LIMIT] if sc >= SEED_MIN_DIRECT}
        expansion = expand(
            graph,
            seeds,
            max_depth=expansion_depth,
            test_boost=1.0 if analysis.wants_tests else 0.5,
        )
        for path, exp in expansion.items():
            breakdowns[path].dependency = min(1.0, exp.score)
        # Code a test must be "linked" to: seeds and strongly-propagated dependencies.
        focus_nodes = {file_node(p) for p in seeds} | {
            file_node(p)
            for p, e in expansion.items()
            if e.score >= TEST_LINK_MIN and by_path[p].file_type == "source"
        }
    else:
        seeds, focus_nodes = {}, set()

    config_requested = bool(analysis.config_terms)
    linked_tests: set[str] = set()
    for path, s in breakdowns.items():
        f = by_path[path]
        if f.file_type == "test":
            linked = any(
                "tests" in d.get("relations", [d.get("relation")]) and v in focus_nodes
                for _, v, d in graph.out_edges(file_node(path), data=True)
            )
            if linked:
                linked_tests.add(path)
            if analysis.wants_tests:
                s.test = 1.0 if linked else 0.4
            else:
                s.test = 0.3 if linked else 0.0
        if f.file_type == "config":
            if config_requested or s.dependency > 0:
                s.config = 1.0
            elif s.lexical > 0:
                s.config = 0.4

    w = weights.model_dump()
    if not semantic_scores:
        w["semantic"] = 0.0
    if not use_dependency:
        w["dependency"] = 0.0
    total_w = sum(w.values()) or 1.0

    docs_requested = "markdown" in analysis.file_type_hints
    candidates: list[Candidate] = []
    for path, s in breakdowns.items():
        combined = sum(w[k] * getattr(s, k) for k in w) / total_w
        if combined <= 0:
            continue
        f = by_path[path]
        hit = hits.get(path)
        exp = expansion.get(path)
        reasons = []
        if f.file_type == "docs" and not docs_requested:
            combined *= DOCS_PRIOR
            reasons.append(f"documentation prior x{DOCS_PRIOR} (task does not mention docs)")
        if hit:
            reasons.append(
                f"BM25 match on {', '.join(hit.matched_terms[:6])} (normalised {s.lexical:.2f})"
            )
        if s.filename >= 0.5:
            reasons.append(f"path/filename matches task terms ({s.filename:.2f})")
        if hit and hit.matched_symbols:
            names = [sid.split("::", 1)[1] for sid in hit.matched_symbols[:3]]
            reasons.append(f"relevant symbols: {', '.join(names)}")
        if path in seeds:
            reasons.append("direct match used as a graph-expansion seed")
        if exp:
            reasons.append(
                f"dependency: {' -> '.join(exp.via)} [{exp.relation}, {exp.confidence} confidence]"
            )
        if s.test > 0:
            reasons.append(
                "test file linked to relevant code"
                if path in linked_tests
                else "test file (task requests tests)"
            )
        if s.config > 0:
            reasons.append("configuration relevant to task/dependencies")
        if s.semantic > 0:
            reasons.append(f"semantic similarity {s.semantic:.2f}")
        candidates.append(
            Candidate(
                path=path,
                file_type=f.file_type,
                language=f.language,
                tokens=f.tokens,
                raw_bm25=hit.score if hit else 0.0,
                scores=ScoreBreakdown(**{k: round(v, 4) for k, v in s.model_dump().items()}),
                combined=round(combined, 6),
                matched_terms=hit.matched_terms if hit else [],
                matched_symbols=hit.matched_symbols if hit else [],
                dependency_path=exp.via if exp else [],
                dependency_relation=exp.relation if exp else None,
                dependency_confidence=exp.confidence if exp else None,
                reasons=reasons,
            )
        )
    candidates.sort(key=lambda c: (-c.combined, c.path))
    return candidates, expansion
