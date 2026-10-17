"""Walk a repository safely and produce indexed files plus an indexing report.

Safety properties:
* repository code is only *read*, never imported or executed;
* symbolic links are never followed outside the root (directory links are not
  followed at all; file links are read only if they resolve inside the root);
* sensitive filenames are skipped without reading, and files whose contents look
  like they contain secrets are excluded without logging the matched value.
"""

from __future__ import annotations

import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.context.token_counter import get_token_counter
from app.core.config import Settings
from app.core.exceptions import InvalidRepositoryError
from app.core.logging_config import get_logger
from app.core.models import ExcludedFile, IndexingReport, RepoFile
from app.ingestion import file_filter
from app.ingestion.language_detector import detect_file_type, detect_language
from app.utils.file_hashing import sha256_text
from app.utils.security import detect_secret, is_within

log = get_logger("scanner")


@dataclass
class ScanResult:
    root: Path
    files: list[RepoFile]
    report: IndexingReport


def scan_repository(root: Path, settings: Settings) -> ScanResult:
    """Scan ``root`` (already validated against allowed roots by the caller)."""
    started = time.perf_counter()
    root = root.resolve()
    if not root.exists():
        raise InvalidRepositoryError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise InvalidRepositoryError(f"Repository path is not a directory: {root}")

    counter = get_token_counter(settings.tokenizer_encoding)
    report = IndexingReport(root=str(root), tokenizer=f"{counter.method}:{counter.encoding_name}")
    files: list[RepoFile] = []
    gitignore = file_filter.GitIgnoreMatcher()
    total_bytes = 0

    def exclude(rel: str, reason: str) -> None:
        report.excluded.append(ExcludedFile(path=rel, reason=reason))

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir

        if settings.respect_gitignore and ".gitignore" in filenames:
            warning = gitignore.add(rel_dir, current / ".gitignore")
            if warning:
                report.parse_warnings.append(warning)

        kept_dirs = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            full = current / name
            if full.is_symlink():
                exclude(rel + "/", "symbolic-link directory not followed")
            elif file_filter.is_excluded_dir(name, settings.extra_excluded_dirs):
                exclude(rel + "/", "excluded directory (vcs/venv/cache/build)")
            elif settings.respect_gitignore and gitignore.matches(rel, is_dir=True):
                exclude(rel + "/", "ignored by .gitignore")
            else:
                kept_dirs.append(name)
        dirnames[:] = kept_dirs

        for name in sorted(filenames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            full = current / name
            report.total_discovered += 1

            if report.limit_reached:
                report.skipped += 1
                continue
            if full.is_symlink():
                target_ok = is_within(full, root)
                if not target_ok:
                    exclude(rel, "symbolic link pointing outside the repository root")
                    continue
            if reason := file_filter.sensitive_reason(rel):
                exclude(rel, reason)
                continue
            if settings.respect_gitignore and gitignore.matches(rel):
                exclude(rel, "ignored by .gitignore")
                continue
            if file_filter.match_custom_globs(rel, settings.extra_excluded_globs):
                exclude(rel, "matched a configured exclusion rule")
                continue
            if file_filter.is_generated(rel):
                exclude(rel, "generated or lock file")
                continue
            language = detect_language(rel)
            if language is None:
                exclude(rel, "unsupported file type")
                continue
            try:
                size = full.stat().st_size
            except OSError as exc:
                exclude(rel, f"unreadable ({exc.strerror})")
                continue
            if size > settings.max_file_bytes:
                exclude(rel, f"file too large ({size} bytes > {settings.max_file_bytes})")
                continue
            if len(files) >= settings.max_files:
                report.limit_reached = f"max_files limit ({settings.max_files}) reached"
                report.skipped += 1
                continue
            if total_bytes + size > settings.max_total_bytes:
                report.limit_reached = f"max_total_bytes limit ({settings.max_total_bytes}) reached"
                report.skipped += 1
                continue
            try:
                raw = full.read_bytes()
            except OSError as exc:
                exclude(rel, f"unreadable ({exc.strerror})")
                continue
            if file_filter.looks_binary(raw[: file_filter.BINARY_SNIFF_BYTES]):
                exclude(rel, "binary content")
                continue
            text = raw.decode("utf-8", errors="replace")
            if label := detect_secret(text):
                exclude(rel, f"possible secret detected ({label}); contents withheld")
                log.warning("Excluded %s: possible secret (%s)", rel, label)
                continue

            total_bytes += size
            tokens = counter.count(text)
            files.append(
                RepoFile(
                    path=rel,
                    language=language,
                    file_type=detect_file_type(rel, language),
                    size_bytes=size,
                    sha256=sha256_text(text),
                    tokens=tokens,
                    content=text,
                    line_count=text.count("\n") + (0 if text.endswith("\n") or not text else 1),
                )
            )

    files.sort(key=lambda f: f.path)
    report.indexed = len(files)
    report.total_tokens = sum(f.tokens for f in files)
    report.total_bytes = total_bytes
    report.file_types = dict(sorted(Counter(f.file_type for f in files).items()))
    report.languages = dict(sorted(Counter(f.language for f in files).items()))
    report.excluded.sort(key=lambda e: e.path)
    report.parse_warnings.extend(counter.warnings[1:])  # heuristic fallback warning, if any
    report.duration_ms = round((time.perf_counter() - started) * 1000, 2)
    return ScanResult(root=root, files=files, report=report)
