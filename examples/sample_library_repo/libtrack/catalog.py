"""Book catalog: adding books, searching and availability."""

from __future__ import annotations

from libtrack.models import Book
from libtrack.utils.text import normalize, tokens


class Catalog:
    def __init__(self) -> None:
        self.books: dict[str, Book] = {}

    def add_book(self, book: Book) -> Book:
        if book.copies < 1:
            raise ValueError("a book needs at least one copy")
        self.books[book.book_id] = book
        return book

    def get(self, book_id: str) -> Book:
        try:
            return self.books[book_id]
        except KeyError:
            raise KeyError(f"unknown book {book_id}") from None

    def search(self, query: str) -> list[Book]:
        """Books whose title or author contains every query word (case/accent-insensitive)."""
        wanted = tokens(query)
        if not wanted:
            return []
        hits = [
            b for b in self.books.values()
            if wanted <= tokens(b.title) | tokens(b.author)
        ]
        return sorted(hits, key=lambda b: normalize(b.title))

    def available_copies(self, book_id: str, open_loans: int) -> int:
        return self.get(book_id).copies - open_loans
