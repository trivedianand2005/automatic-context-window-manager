import pytest

from libtrack.catalog import Catalog
from libtrack.models import Book


def test_search_is_case_and_accent_insensitive(service):
    assert [b.book_id for b in service.catalog.search("cafe LOPEZ")] == ["b2"]


def test_search_requires_all_words(service):
    assert service.catalog.search("clean stories") == []


def test_book_needs_a_copy():
    with pytest.raises(ValueError):
        Catalog().add_book(Book("x", "T", "A", "1", copies=0))
