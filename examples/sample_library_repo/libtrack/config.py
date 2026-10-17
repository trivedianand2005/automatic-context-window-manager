"""Library policy settings, read from environment variables with safe defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    loan_days: int = field(default_factory=lambda: _int("LIBTRACK_LOAN_DAYS", 14))
    fine_per_day_cents: int = field(default_factory=lambda: _int("LIBTRACK_FINE_PER_DAY", 25))
    max_fine_cents: int = field(default_factory=lambda: _int("LIBTRACK_MAX_FINE", 2000))
    max_loans_per_member: int = field(default_factory=lambda: _int("LIBTRACK_MAX_LOANS", 5))
    data_file: str = field(default_factory=lambda: os.getenv("LIBTRACK_DATA", "library.json"))
    email_sender: str = "noreply@libtrack.example"


def get_settings() -> Settings:
    return Settings()
