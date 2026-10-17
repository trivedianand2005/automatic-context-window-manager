from datetime import timedelta

import pytest

from libtrack.loans import LoanError


def test_checkout_sets_due_date(service, today):
    loan = service.checkout("b1", "m1", today)
    assert loan.due_on == today + timedelta(days=14)


def test_no_copies_left(service, today):
    service.checkout("b1", "m1", today)
    with pytest.raises(LoanError, match="no copies"):
        service.checkout("b1", "m2", today)


def test_loan_limit(service, today):
    service.checkout("b2", "m1", today)
    service.checkout("b2", "m1", today)
    with pytest.raises(LoanError, match="limit"):
        service.checkout("b1", "m1", today)


def test_suspended_member(service, today):
    service.members.suspend("m2")
    with pytest.raises(LoanError, match="suspended"):
        service.checkout("b1", "m2", today)


def test_return_records_fine(service, today):
    loan = service.checkout("b1", "m1", today)
    returned = service.return_book(loan.loan_id, loan.due_on + timedelta(days=4))
    assert returned.fine_cents > 0 and not returned.is_open


def test_renew_extends_due_date(service, today):
    loan = service.checkout("b1", "m1", today)
    old_due = loan.due_on
    assert service.renew(loan.loan_id, today).due_on == old_due + timedelta(days=14)
