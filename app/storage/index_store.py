"""In-memory store of indexed repositories (process-local, thread-safe)."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from app.core.exceptions import RepositoryNotFoundError
from app.core.models import IndexingReport, ModuleInfo, RepoFile, ResolvedImport
from app.retrieval.lexical_search import LexicalIndex


@dataclass
class IndexedRepository:
    repository_id: str
    root: Path
    fingerprint: str
    files: dict[str, RepoFile]
    modules: dict[str, ModuleInfo]
    resolved_imports: list[ResolvedImport]
    graph: nx.DiGraph
    lexical: LexicalIndex
    report: IndexingReport
    encoding: str
    created_at: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def symbol_count(self) -> int:
        return sum(len(m.symbols) for m in self.modules.values())


class IndexStore:
    def __init__(self, max_repositories: int = 8) -> None:
        self._items: OrderedDict[str, IndexedRepository] = OrderedDict()
        self._lock = threading.Lock()
        self.max_repositories = max_repositories

    def put(self, repo: IndexedRepository) -> None:
        with self._lock:
            self._items[repo.repository_id] = repo
            self._items.move_to_end(repo.repository_id)
            while len(self._items) > self.max_repositories:
                self._items.popitem(last=False)

    def get(self, repository_id: str) -> IndexedRepository:
        with self._lock:
            repo = self._items.get(repository_id)
        if repo is None:
            raise RepositoryNotFoundError(
                f"Repository '{repository_id}' is not indexed. Index it first."
            )
        return repo

    def list(self) -> list[IndexedRepository]:
        with self._lock:
            return list(self._items.values())
