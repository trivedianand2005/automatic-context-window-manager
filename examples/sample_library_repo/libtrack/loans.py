"""Borrowing, returning and renewing books."""

from __future__ import annotations

import itertools
from datetime import date

from libtrack.catalog import Catalog
from libtrack.config import Settings, get_settings
from libtrack.fines import calculate_fine
from libtrack.members import MemberRegistry
from libtrack.models import Loan
from libtrack.utils.dates import add_days


class LoanError(Exception):
    """A loan rule was violated."""


class LoanService:
    def __init__(self, catalog: Catalog, members: MemberRegistry,
                 settings: Settings | None = None) -> None:
        self.catalog = catalog
        self.members = members
        self.settings = settings or get_settings()
        self.loans: list[Loan] = []
        self._ids = itertools.count(1)

    def open_loans_for_book(self, book_id: str) -> int:
        return sum(1 for loan in self.loans if loan.book_id == book_id and loan.is_open)

    def open_loans_for_member(self, member_id: str) -> list[Loan]:
        return [loan for loan in self.loans if loan.member_id == member_id and loan.is_open]

    def checkout(self, book_id: str, member_id: str, today: date) -> Loan:
        member = self.members.get(member_id)
        if member.suspended:
            raise LoanError("member is suspended")
        if len(self.open_loans_for_member(member_id)) >= self.settings.max_loans_per_member:
            raise LoanError("member has reached the loan limit")
        if self.catalog.available_copies(book_id, self.open_loans_for_book(book_id)) <= 0:
            raise LoanError("no copies available")
        loan = Loan(next(self._ids), book_id, member_id, today,
                    add_days(today, self.settings.loan_days))
        self.loans.append(loan)
        return loan

    def return_book(self, loan_id: int, today: date) -> Loan:
        loan = self._get_open(loan_id)
        loan.returned_on = today
        loan.fine_cents = calculate_fine(loan.due_on, today, self.settings)
        return loan

    def renew(self, loan_id: int, today: date) -> Loan:
        """Extend the due date. There is currently no limit on the number of renewals."""
        loan = self._get_open(loan_id)
        if today > loan.due_on:
            raise LoanError("overdue loans cannot be renewed")
        loan.due_on = add_days(loan.due_on, self.settings.loan_days)
        loan.renewals += 1
        return loan

    def overdue(self, today: date) -> list[Loan]:
        return [loan for loan in self.loans if loan.is_open and loan.due_on < today]

    def _get_open(self, loan_id: int) -> Loan:
        for loan in self.loans:
            if loan.loan_id == loan_id and loan.is_open:
                return loan
        raise LoanError(f"no open loan {loan_id}")
