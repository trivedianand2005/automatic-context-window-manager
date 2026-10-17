"""BM25 lexical retrieval over files and extracted symbols (``rank_bm25.BM25Okapi``).

File documents weight structural text higher by repetition: path tokens x3,
symbol names x2, then docstrings, imports and the raw source/documentation text.
Results are sorted by (score desc, path asc) for deterministic output.

IDF uses the Lucene/ATIRE form ``log(1 + (N - n + 0.5) / (n + 0.5))``, which is always
positive. The classic Okapi form becomes <= 0 for terms present in at least half of
the documents, which zeroes out genuine matches in small repositories.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import PurePosixPath

from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi

from app.analysis.text_processing import tokenize
from app.core.models import ModuleInfo, RepoFile, Symbol

SECONDARY_TERM_WEIGHT = 0.5


class PositiveIDFBM25(BM25Okapi):
    """BM25Okapi with a strictly positive (Lucene-style) IDF."""

    def _calc_idf(self, nd: dict[str, int]) -> None:
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))


class LexicalHit(BaseModel):
    path: str
    score: float
    matched_terms: list[str] = Field(default_factory=list)
    matched_symbols: list[str] = Field(default_factory=list)
    symbol_scores: dict[str, float] = Field(default_factory=dict)


def _file_document(f: RepoFile, info: ModuleInfo | None) -> list[str]:
    path_terms = tokenize(PurePosixPath(f.path).as_posix().replace("/", " "))
    terms = path_terms * 3
    if info is not None:
        if info.docstring:
            terms += tokenize(info.docstring)
        for sym in info.symbols:
            terms += tokenize(sym.name) * 2
            if sym.docstring:
                terms += tokenize(sym.docstring)
        for imp in info.imports:
            terms += tokenize(" ".join([imp.module, *imp.names]))
    terms += tokenize(f.content)
    return terms or ["__empty__"]


def _symbol_document(sym: Symbol, source: str) -> list[str]:
    lines = source.splitlines()[sym.start_line - 1 : sym.end_line]
    body = "\n".join(lines[:200])
    terms = tokenize(sym.name) * 3 + tokenize(sym.qualname) + tokenize(sym.signature)
    if sym.docstring:
        terms += tokenize(sym.docstring)
    terms += tokenize(body)
    return terms or ["__empty__"]


class LexicalIndex:
    def __init__(self, files: list[RepoFile], modules: dict[str, ModuleInfo]) -> None:
        self.files = sorted(files, key=lambda f: f.path)
        self.paths = [f.path for f in self.files]
        file_docs = [_file_document(f, modules.get(f.path)) for f in self.files]
        self._file_terms = [set(doc) for doc in file_docs]
        self._file_bm25 = PositiveIDFBM25(file_docs) if file_docs else None

        self.symbols: list[Symbol] = []
        sym_docs: list[list[str]] = []
        contents = {f.path: f.content for f in self.files}
        for path in self.paths:
            info = modules.get(path)
            if info is None:
                continue
            for sym in info.symbols:
                self.symbols.append(sym)
                sym_docs.append(_symbol_document(sym, contents[path]))
        self._sym_terms = [set(doc) for doc in sym_docs]
        self._sym_bm25 = PositiveIDFBM25(sym_docs) if sym_docs else None
        self.vocabulary = Counter(t for terms in self._file_terms for t in terms)

    @staticmethod
    def _weighted_scores(bm25: PositiveIDFBM25, primary: list[str], secondary: list[str]):
        scores = bm25.get_scores(primary) if primary else None
        if secondary:
            sec = bm25.get_scores(secondary) * SECONDARY_TERM_WEIGHT
            scores = sec if scores is None else scores + sec
        return scores

    def search(
        self, primary: list[str], secondary: list[str] | None = None, limit: int | None = None
    ) -> list[LexicalHit]:
        secondary = secondary or []
        if self._file_bm25 is None or not (primary or secondary):
            return []
        file_scores = self._weighted_scores(self._file_bm25, primary, secondary)
        query = set(primary) | set(secondary)

        per_file_symbols: dict[str, list[tuple[float, str]]] = {}
        if self._sym_bm25 is not None:
            sym_scores = self._weighted_scores(self._sym_bm25, primary, secondary)
            for sym, score, terms in zip(self.symbols, sym_scores, self._sym_terms, strict=True):
                if score > 0 and terms & query:
                    per_file_symbols.setdefault(sym.path, []).append((float(score), sym.id))

        hits: list[LexicalHit] = []
        for path, score, terms in zip(self.paths, file_scores, self._file_terms, strict=True):
            matched = sorted(terms & query)
            if not matched:
                continue
            ranked_syms = sorted(per_file_symbols.get(path, []), key=lambda x: (-x[0], x[1]))[:5]
            hits.append(
                LexicalHit(
                    path=path,
                    score=round(max(float(score), 0.0), 6),
                    matched_terms=matched,
                    matched_symbols=[sid for _, sid in ranked_syms],
                    symbol_scores={sid: round(s, 4) for s, sid in ranked_syms},
                )
            )
        hits.sort(key=lambda h: (-h.score, h.path))
        return hits[:limit] if limit else hits
