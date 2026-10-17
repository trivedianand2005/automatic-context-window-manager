from datetime import date

import pytest

from libtrack.catalog import Catalog
from libtrack.config import Settings
from libtrack.loans import LoanService
from libtrack.members import MemberRegistry
from libtrack.models import Book


@pytest.fixture()
def settings():
    return Settings(loan_days=14, fine_per_day_cents=25, max_fine_cents=500, max_loans_per_member=2)


@pytest.fixture()
def service(settings):
    catalog = Catalog()
    catalog.add_book(Book("b1", "Clean Code", "Robert Martin", "9780132350884", copies=1))
    catalog.add_book(Book("b2", "Café Stories", "Ana López", "9780000000002", copies=3))
    members = MemberRegistry()
    members.register("m1", "Reader One", "one@example.com")
    members.register("m2", "Reader Two", "two@example.com")
    return LoanService(catalog, members, settings)


@pytest.fixture()
def today():
    return date(2026, 1, 1)
