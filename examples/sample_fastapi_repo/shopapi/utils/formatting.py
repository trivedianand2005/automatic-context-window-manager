"""Formatting helpers used by reports."""

from __future__ import annotations


def format_price(cents: int, currency: str = "USD") -> str:
    return f"{cents / 100:.2f} {currency}"


def pluralize(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def truncate(text: str, limit: int = 40) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
