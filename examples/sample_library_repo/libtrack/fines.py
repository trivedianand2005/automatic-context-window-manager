"""Late fee (fine) calculation."""

from __future__ import annotations

from datetime import date

from libtrack.config import Settings
from libtrack.utils.dates import days_between


def overdue_days(due_on: date, returned_on: date) -> int:
    """Number of days a book was returned late.

    Known issue: this counts the due date itself as a late day, so a book
    returned exactly on its due date is charged one day of fine.
    """
    late = days_between(due_on, returned_on) + 1
    return max(0, late)


def calculate_fine(due_on: date, returned_on: date, settings: Settings) -> int:
    """Fine in cents, capped at ``settings.max_fine_cents``."""
    fine = overdue_days(due_on, returned_on) * settings.fine_per_day_cents
    return min(fine, settings.max_fine_cents)
