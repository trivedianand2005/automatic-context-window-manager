"""Usage statistics for the monthly library report.

Provides fine-grained statistics (per book, per member, per day). These are
reporting helpers only; late fees themselves are calculated elsewhere.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from libtrack.models import Loan


def most_borrowed(loans: list[Loan], top: int = 5) -> list[tuple[str, int]]:
    """Fine-grained popularity ranking of books by number of loans."""
    return Counter(loan.book_id for loan in loans).most_common(top)


def busiest_members(loans: list[Loan], top: int = 5) -> list[tuple[str, int]]:
    return Counter(loan.member_id for loan in loans).most_common(top)


def loans_per_day(loans: list[Loan]) -> dict[date, int]:
    """Daily loan counts, fine-grained enough for a heatmap."""
    counts: Counter[date] = Counter(loan.borrowed_on for loan in loans)
    return dict(sorted(counts.items()))


def total_fines_collected(loans: list[Loan]) -> int:
    """Sum of fines already charged (in cents) for the report's summary line."""
    return sum(loan.fine_cents for loan in loans if not loan.is_open)


def summary(loans: list[Loan]) -> str:
    returned = sum(1 for loan in loans if not loan.is_open)
    return (f"{len(loans)} loans, {returned} returned, "
            f"{total_fines_collected(loans) / 100:.2f} collected in fines")
