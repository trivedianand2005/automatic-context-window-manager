"""Date helpers."""

from __future__ import annotations

from datetime import date, timedelta


def parse_date(text: str) -> date:
    """Parse an ISO date (YYYY-MM-DD)."""
    return date.fromisoformat(text.strip())


def add_days(start: date, days: int) -> date:
    return start + timedelta(days=days)


def days_between(start: date, end: date) -> int:
    """Whole days from ``start`` to ``end`` (0 when equal, negative if end is earlier)."""
    return (end - start).days
