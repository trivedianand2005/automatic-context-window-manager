"""Text normalisation used by catalog search."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase, strip accents and collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_only).strip().lower()


def tokens(text: str) -> set[str]:
    return set(normalize(text).split())
