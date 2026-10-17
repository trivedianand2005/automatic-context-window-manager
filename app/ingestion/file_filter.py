"""Decide which discovered files may be indexed, and why others are excluded."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pathspec

from app.utils.security import is_sensitive_filename

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "site-packages",
    ".eggs",
    "htmlcov",
    ".acwm",
    "demo_output",
}
GENERATED_GLOBS = ["*.egg-info", "*.min.js", "*.lock", "*.pyc", "*.pyo", "*_pb2.py"]
BINARY_SNIFF_BYTES = 8192


@dataclass
class GitIgnoreMatcher:
    """Hierarchical .gitignore support: each spec applies to paths below its directory."""

    specs: list[tuple[str, pathspec.PathSpec]] = field(default_factory=list)

    def add(self, directory_rel: str, gitignore_path: Path) -> str | None:
        try:
            lines = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return f"Could not read {gitignore_path.name}: {exc.strerror}"
        self.specs.append((directory_rel, pathspec.GitIgnoreSpec.from_lines(lines)))
        return None

    def matches(self, rel_path: str, is_dir: bool = False) -> bool:
        for base, spec in self.specs:
            if base and not (rel_path == base or rel_path.startswith(base + "/")):
                continue
            sub = rel_path[len(base) + 1 :] if base else rel_path
            if not sub:
                continue
            if spec.match_file(sub + ("/" if is_dir else "")):
                return True
        return False


def is_excluded_dir(name: str, extra: list[str] | None = None) -> bool:
    if name in DEFAULT_EXCLUDED_DIRS or name in (extra or []):
        return True
    return name.endswith(".egg-info")


def match_custom_globs(rel_path: str, globs: list[str]) -> bool:
    name = PurePosixPath(rel_path).name
    return any(fnmatch.fnmatch(rel_path, g) or fnmatch.fnmatch(name, g) for g in globs)


def is_generated(rel_path: str) -> bool:
    return match_custom_globs(rel_path, GENERATED_GLOBS)


def looks_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    try:
        sample.decode("utf-8")
        return False
    except UnicodeDecodeError as exc:
        # A multi-byte character cut at the sniff boundary is not evidence of binary data.
        return exc.start < len(sample) - 4


def sensitive_reason(rel_path: str) -> str | None:
    if is_sensitive_filename(rel_path):
        return "sensitive filename (possible credentials); contents not read"
    return None
