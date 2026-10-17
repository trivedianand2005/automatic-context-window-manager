"""Deterministic, dependency-aware greedy selection under a token budget.

Algorithm (n = eligible candidates)
1. Eligibility: drop candidates with combined score < max(ABS_MIN, REL_MIN * top score).
2. Required paths are placed first (full -> excerpt -> outline). If none fits, a
   loud omission is recorded; required files are never dropped silently.
3. Core set: candidates scoring >= CORE_RATIO * top score (at most CORE_LIMIT) are
   placed next in score order, as a full file or, if needed, an excerpt. This keeps
   the most relevant (often larger) files from being crowded out by many small files.
   If the core set does not fit in full, each core file is limited to a fair share
   (1.5 x remaining / core files left) so that coverage beats completeness.
4. Repeat until nothing fits:
     for every remaining candidate choose a variant:
        full file   if it fits the remaining budget and the per-file cap
        excerpt     (relevant symbols + outline) otherwise, if it fits
     utility  = combined * variant_factor * (1 + DEP_BONUS if graph-adjacent to a
                selected file) * redundancy_factor
     priority = utility / tokens ** DENSITY_EXPONENT
     select the highest priority (ties broken by path).
5. The caller re-renders and validates the final package against the usable budget.

The exponent (0.5) tempers pure relevance-per-token so tiny files do not crowd out
large-but-central ones, and the per-file cap stops one huge file from consuming the
budget when an excerpt would carry most of its value.

Complexity: O(n^2) priority evaluations (n is small after eligibility filtering);
excerpt construction is cached per candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from app.context.summarizer import Excerpt, build_excerpt, python_outline
from app.context.token_counter import BudgetPlan, TokenCounter
from app.core.models import Candidate, ModuleInfo, RepoFile
from app.graph.dependency_graph import file_node

ABS_MIN_SCORE = 0.04
REL_MIN_SCORE = 0.3
DENSITY_EXPONENT = 0.5
MAX_FULL_FILE_FRACTION = 0.4
DEPENDENCY_BONUS = 0.25
VARIANT_FACTOR = {"full": 1.0, "excerpt": 0.85, "outline": 0.5}
REDUNDANCY_THRESHOLD = 0.5
DUPLICATE_THRESHOLD = 0.9
CORE_RATIO = 0.5
CORE_LIMIT = 12
FAIR_SHARE_SLACK = 1.5


@dataclass
class Selection:
    candidate: Candidate
    kind: str  # full | excerpt | outline
    content: str
    tokens: int
    line_ranges: list[tuple[int, int]]
    symbols: list[str]
    note: str
    required: bool = False


@dataclass
class OptimizationResult:
    selected: list[Selection] = field(default_factory=list)
    excluded: list[tuple[Candidate, str]] = field(default_factory=list)
    omissions: list[str] = field(default_factory=list)
    used_tokens: int = 0


@dataclass
class OptimizerOptions:
    redundancy_penalty: bool = True
    allow_excerpts: bool = True
    dependency_aware: bool = True
    max_full_file_fraction: float = MAX_FULL_FILE_FRACTION
    rel_min_score: float = REL_MIN_SCORE


def _line_set(text: str) -> set[str]:
    return {ln.strip() for ln in text.splitlines() if len(ln.strip()) > 8}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class BudgetOptimizer:
    def __init__(
        self,
        files: dict[str, RepoFile],
        modules: dict[str, ModuleInfo],
        graph: nx.DiGraph,
        counter: TokenCounter,
        plan: BudgetPlan,
        query_terms: set[str],
        options: OptimizerOptions | None = None,
    ) -> None:
        self.files = files
        self.modules = modules
        self.graph = graph
        self.counter = counter
        self.plan = plan
        self.query_terms = query_terms
        self.options = options or OptimizerOptions()
        self._excerpt_cache: dict[str, list[Excerpt]] = {}
        self._line_sets: dict[str, set[str]] = {}

    def _cost(self, text: str) -> int:
        return self.counter.count(text) + self.plan.per_item_overhead_tokens

    def _excerpts(self, cand: Candidate) -> list[Excerpt]:
        """Progressively smaller excerpts: top-5/2/1 matched symbols with a bounded outline,
        the top symbol alone, then a signature outline."""
        if cand.path not in self._excerpt_cache:
            f, info = self.files[cand.path], self.modules.get(cand.path)
            ladder: list[Excerpt] = []
            seen: set[str] = set()
            if cand.matched_symbols:
                rungs = [(cand.matched_symbols[:n], 25) for n in (5, 2, 1)]
                rungs.append((cand.matched_symbols[:1], 0))  # focus symbol only, no outline
            else:
                rungs = [([], 25)]
            for focus, outline_limit in rungs:
                ex = build_excerpt(f, info, focus, self.query_terms, outline_limit)
                if ex.content not in seen:
                    seen.add(ex.content)
                    ladder.append(ex)
            if info is not None and info.symbols and info.parse_error is None:
                outline = python_outline(f, info)
                if outline.content not in seen:
                    ladder.append(outline)
            self._excerpt_cache[cand.path] = ladder
        return self._excerpt_cache[cand.path]

    def _variants(self, cand: Candidate, remaining: int, cap: int, force: bool = False):
        """Yield (kind, content, tokens, ranges, symbols, note) in preference order."""
        f = self.files[cand.path]
        full_cost = self._cost(f.content)
        if full_cost <= remaining and (full_cost <= cap or force):
            yield (
                "full",
                f.content,
                full_cost,
                [(1, f.line_count)] if f.line_count else [],
                [],
                (f"full file ({full_cost} tokens)"),
            )
        if not (self.options.allow_excerpts or force):
            return
        why = "exceeds per-file cap" if full_cost > cap else "does not fit remaining budget"
        for ex in self._excerpts(cand):
            if not ex.content.strip() or ex.content == f.content:
                continue
            cost = self._cost(ex.content)
            if cost <= remaining and cost < full_cost:
                yield (
                    ex.kind,
                    ex.content,
                    cost,
                    ex.line_ranges,
                    ex.symbols,
                    (f"{ex.kind} ({cost} tokens) because full file ({full_cost} tokens) {why}"),
                )

    def _max_overlap(self, content: str, selected: list[Selection]) -> tuple[float, str]:
        """Highest line-set Jaccard overlap between ``content`` and already-selected content."""
        if not self.options.redundancy_penalty or not selected:
            return 0.0, ""
        lines = _line_set(content)
        best = (0.0, "")
        for s in selected:
            other = self._line_sets.setdefault(s.candidate.path, _line_set(s.content))
            best = max(best, (_jaccard(lines, other), s.candidate.path))
        return best

    def _adjacent_to_selection(self, path: str, selected_paths: set[str]) -> bool:
        node = file_node(path)
        if node not in self.graph:
            return False
        neighbours = set(self.graph.successors(node)) | set(self.graph.predecessors(node))
        return any(file_node(p) in neighbours for p in selected_paths)

    def optimize(
        self, candidates: list[Candidate], required_paths: list[str] | None = None
    ) -> OptimizationResult:
        result = OptimizationResult()
        usable = self.plan.usable_tokens
        cap = max(1, int(usable * self.options.max_full_file_fraction))
        required = [p for p in dict.fromkeys(required_paths or [])]
        by_path = {c.path: c for c in candidates}
        selected_paths: set[str] = set()

        for path in required:
            cand = by_path.get(path)
            if cand is None and path in self.files:
                f = self.files[path]
                cand = Candidate(
                    path=path,
                    file_type=f.file_type,
                    language=f.language,
                    tokens=f.tokens,
                    reasons=["required by user"],
                )
            if cand is None:
                result.omissions.append(f"REQUIRED file '{path}' is not in the index.")
                continue
            remaining = usable - result.used_tokens
            choice = next(iter(self._variants(cand, remaining, cap, force=True)), None)
            if choice is None:
                result.omissions.append(
                    f"REQUIRED file '{path}' ({cand.tokens} tokens) could not fit in the "
                    f"remaining budget ({remaining} tokens), even as an outline."
                )
                result.excluded.append((cand, "required but does not fit even as outline"))
                continue
            kind, content, cost, ranges, syms, note = choice
            result.selected.append(
                Selection(
                    cand,
                    kind,
                    content,
                    cost,
                    ranges,
                    syms,
                    note + "; required by user",
                    required=True,
                )
            )
            result.used_tokens += cost
            selected_paths.add(path)

        top = max((c.combined for c in candidates), default=0.0)
        threshold = max(ABS_MIN_SCORE, self.options.rel_min_score * top)
        pool: list[Candidate] = []
        for cand in candidates:
            if cand.path in selected_paths:
                continue
            if cand.combined < threshold:
                result.excluded.append(
                    (cand, f"below relevance threshold ({cand.combined:.3f} < {threshold:.3f})")
                )
            else:
                pool.append(cand)

        core = [c for c in pool if c.combined >= CORE_RATIO * top][:CORE_LIMIT]
        core_full_cost = sum(self._cost(self.files[c.path].content) for c in core)
        constrained = core_full_cost > usable - result.used_tokens
        for idx, cand in enumerate(core):
            remaining = usable - result.used_tokens
            variant = None
            if constrained:
                # Fair share: favour covering every core file (possibly as an excerpt)
                # over including a few of them in full.
                share = int(FAIR_SHARE_SLACK * remaining / (len(core) - idx))
                variant = next(
                    iter(self._variants(cand, min(remaining, share), min(cap, share))), None
                )
            if variant is None:
                variant = next(iter(self._variants(cand, remaining, cap)), None)
            if variant is None:
                continue
            if self._max_overlap(variant[1], result.selected)[0] >= REDUNDANCY_THRESHOLD:
                continue  # near-duplicates are handled by the penalised greedy phase
            kind, content, cost, ranges, syms, note = variant
            note += f"; core candidate (score >= {CORE_RATIO:.0%} of top score)"
            if constrained:
                note += "; fair-share allocation (core set exceeds budget)"
            result.selected.append(Selection(cand, kind, content, cost, ranges, syms, note))
            result.used_tokens += cost
            selected_paths.add(cand.path)
            pool.remove(cand)

        while pool:
            remaining = usable - result.used_tokens
            best = None
            for cand in list(pool):
                variant = next(iter(self._variants(cand, remaining, cap)), None)
                if variant is None:
                    continue
                kind, content, cost, ranges, syms, note = variant
                overlap, twin = self._max_overlap(content, result.selected)
                if overlap >= DUPLICATE_THRESHOLD:
                    pool.remove(cand)
                    result.excluded.append(
                        (cand, f"near-duplicate of selected {twin} ({overlap:.2f} line overlap)")
                    )
                    continue
                utility = cand.combined * VARIANT_FACTOR[kind]
                extra = []
                if self.options.dependency_aware and self._adjacent_to_selection(
                    cand.path, selected_paths
                ):
                    utility *= 1 + DEPENDENCY_BONUS
                    extra.append("dependency bonus (adjacent to selected file)")
                if overlap >= REDUNDANCY_THRESHOLD:
                    utility *= 1 - overlap
                    extra.append(f"redundancy penalty ({overlap:.2f} line overlap with {twin})")
                priority = utility / (max(cost, 1) ** DENSITY_EXPONENT)
                key = (priority, cand.combined, _neg(cand.path))
                if best is None or key > best[0]:
                    best = (key, cand, variant, extra)
            if best is None:
                break
            (priority, _, _), cand, variant, extra = best
            kind, content, cost, ranges, syms, note = variant
            note = "; ".join([note, f"priority {priority:.4f}", *extra])
            result.selected.append(Selection(cand, kind, content, cost, ranges, syms, note))
            result.used_tokens += cost
            selected_paths.add(cand.path)
            pool.remove(cand)

        for cand in pool:
            result.excluded.append(
                (
                    cand,
                    f"does not fit remaining budget ({usable - result.used_tokens} tokens left; "
                    f"full file {cand.tokens} tokens)",
                )
            )
        result.excluded.sort(key=lambda x: (-x[0].combined, x[0].path))
        return result


def _neg(path: str) -> tuple[int, ...]:
    """Tie-breaker that prefers lexicographically smaller paths under max()."""
    return tuple(-ord(ch) for ch in path)
