"""Merge pinned facts: dedupe near-duplicates, and the newer fact wins on a conflict.

Two facts conflict when they share a topic key (the text before ':' in "topic: value").
Two facts are duplicates when their word sets overlap by at least DUPLICATE_JACCARD.
In both cases the older fact is dropped and the newer wording is kept.
"""

from __future__ import annotations

import re

from app.conversation.models import Fact

DUPLICATE_JACCARD = 0.8
MAX_KEY_WORDS = 5
MAX_FACT_CHARS = 300
_WORD = re.compile(r"[a-z0-9]+")


def fact_key(text: str) -> str | None:
    head, sep, rest = text.partition(":")
    if not sep or not rest.strip():
        return None
    words = _WORD.findall(head.lower())
    if not 1 <= len(words) <= MAX_KEY_WORDS:
        return None
    return " ".join(words)


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def merge_facts(existing: list[Fact], new: list[str], turn: int) -> list[Fact]:
    """Return ``existing`` updated with ``new`` (later items in ``new`` count as newer)."""
    merged = list(existing)
    for raw in new:
        text = " ".join(raw.split())[:MAX_FACT_CHARS]
        if not text:
            continue
        key = fact_key(text)
        words = _words(text)
        merged = [
            f
            for f in merged
            if not (key and f.key == key) and _jaccard(_words(f.text), words) < DUPLICATE_JACCARD
        ]
        merged.append(Fact(text=text, turn=turn, key=key))
    return merged
