"""Record recent task runs (metadata only; never file contents)."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path

from pydantic import BaseModel


class RunRecord(BaseModel):
    timestamp: float
    repository_id: str
    task: str
    mode: str
    selected_files: int
    rendered_tokens: int
    usable_tokens: int
    latency_ms: float


class SessionStore:
    def __init__(self, max_runs: int = 50, persist_path: Path | None = None) -> None:
        self._runs: deque[RunRecord] = deque(maxlen=max_runs)
        self._lock = threading.Lock()
        self.persist_path = persist_path

    def record(self, run: RunRecord) -> None:
        with self._lock:
            self._runs.appendleft(run)
            if self.persist_path is not None:
                try:
                    self.persist_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.persist_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(run.model_dump()) + "\n")
                except OSError:
                    pass  # persistence is best-effort

    def recent(self, limit: int = 10) -> list[RunRecord]:
        with self._lock:
            return list(self._runs)[:limit]

    @staticmethod
    def now() -> float:
        return time.time()
