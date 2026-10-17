"""Domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Book:
    book_id: str
    title: str
    author: str
    isbn: str
    copies: int = 1


@dataclass
class Member:
    member_id: str
    name: str
    email: str
    suspended: bool = False


@dataclass
class Loan:
    loan_id: int
    book_id: str
    member_id: str
    borrowed_on: date
    due_on: date
    returned_on: date | None = None
    renewals: int = 0
    fine_cents: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.returned_on is None
