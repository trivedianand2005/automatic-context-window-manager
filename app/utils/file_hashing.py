"""Deterministic hashing helpers for files and repository fingerprints."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def repository_id_for(root: str) -> str:
    """Stable id derived from the normalised absolute root path."""
    return hashlib.sha256(root.lower().encode("utf-8")).hexdigest()[:16]


def fingerprint(file_hashes: Iterable[tuple[str, str]]) -> str:
    """Combine (path, hash) pairs into one content fingerprint, order-independent."""
    digest = hashlib.sha256()
    for path, file_hash in sorted(file_hashes):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]
