"""Tokenisation shared by the task analyzer and the BM25 index (code-aware)."""

from __future__ import annotations

import re

STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "then",
    "else",
    "for",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "with",
    "from",
    "into",
    "onto",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "there",
    "here",
    "we",
    "our",
    "you",
    "your",
    "i",
    "me",
    "my",
    "they",
    "them",
    "their",
    "he",
    "she",
    "his",
    "her",
    "do",
    "does",
    "did",
    "done",
    "can",
    "could",
    "should",
    "would",
    "will",
    "shall",
    "may",
    "might",
    "must",
    "so",
    "such",
    "some",
    "any",
    "all",
    "each",
    "every",
    "no",
    "not",
    "only",
    "also",
    "too",
    "very",
    "just",
    "more",
    "most",
    "less",
    "than",
    "when",
    "where",
    "which",
    "who",
    "whom",
    "what",
    "why",
    "how",
    "about",
    "after",
    "before",
    "over",
    "under",
    "again",
    "please",
    "make",
    "sure",
    "need",
    "needs",
    "want",
    "wants",
    "like",
    "using",
    "use",
    "via",
    "new",
    "add",
    "adds",
    "added",
    "create",
    "creates",
    "implement",
    "implements",
    "update",
    "improve",
    "improves",
    "fix",
    "fixes",
    "change",
    "changes",
    "support",
    "ensure",
    "write",
    "self",
    "none",
    "true",
    "false",
    "return",
    "def",
    "class",
    "import",
    "pass",
    "str",
    "int",
    "app",
    "application",
    "code",
    "file",
    "files",
}
# Short tokens that are meaningful in code tasks.
SHORT_KEEP = {"db", "id", "ui", "io", "ip", "jwt", "api", "sql", "orm", "env", "url", "cli", "ttl"}

_CAMEL_1 = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_2 = re.compile(r"([a-z0-9])([A-Z])")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def split_identifier(token: str) -> list[str]:
    spaced = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", token))
    return [p.lower() for p in re.split(r"[\s_\-./]+", spaced) if p]


def stem(word: str) -> str:
    """Very light, deterministic suffix stripping (keeps technical terms intact)."""
    if len(word) <= 4 or word in SHORT_KEEP:
        return word
    for suffix, repl in (
        ("ies", "y"),
        ("sses", "ss"),
        ("ing", ""),
        ("ed", ""),
        ("es", ""),
        ("s", ""),
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix == "es" and not word.endswith(("ches", "shes", "xes", "sses", "zes")):
                continue
            if suffix == "s" and word.endswith("ss"):
                continue
            return word[: -len(suffix)] + repl
    return word


def tokenize(text: str, keep_stop_words: bool = False) -> list[str]:
    """Split text/code into lowercase stemmed terms, splitting snake_case and CamelCase."""
    out: list[str] = []
    for raw in _WORD.findall(text):
        for part in split_identifier(raw):
            if len(part) < 3 and part not in SHORT_KEEP:
                continue
            if not keep_stop_words and part in STOP_WORDS:
                continue
            out.append(stem(part))
    return out
