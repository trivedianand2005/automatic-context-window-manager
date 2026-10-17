"""JSON file persistence with atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"books": {}, "members": {}, "loans": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        """Write to a temporary file first, then replace, so a crash never corrupts data."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        os.replace(tmp, self.path)
