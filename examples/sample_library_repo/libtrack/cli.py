"""Command-line interface (demo data only)."""

from __future__ import annotations

import argparse
from datetime import date

from libtrack.catalog import Catalog
from libtrack.loans import LoanService
from libtrack.members import MemberRegistry
from libtrack.models import Book
from libtrack.utils.dates import parse_date


def build_demo() -> LoanService:
    catalog = Catalog()
    catalog.add_book(Book("b1", "Clean Code", "Robert Martin", "9780132350884", copies=2))
    catalog.add_book(Book("b2", "The Pragmatic Programmer", "Hunt & Thomas", "9780201616224"))
    members = MemberRegistry()
    members.register("m1", "Demo Reader", "reader@example.com")
    return LoanService(catalog, members)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="libtrack")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="search books by title or author")
    search.add_argument("query")
    fine = sub.add_parser("fine", help="show the fine for a return date")
    fine.add_argument("--due", required=True)
    fine.add_argument("--returned", default=str(date.today()))
    args = parser.parse_args(argv)

    service = build_demo()
    if args.command == "search":
        for book in service.catalog.search(args.query):
            print(f"{book.book_id}  {book.title} - {book.author}")
    elif args.command == "fine":
        from libtrack.fines import calculate_fine

        cents = calculate_fine(parse_date(args.due), parse_date(args.returned), service.settings)
        print(f"Fine: ${cents / 100:.2f}")


if __name__ == "__main__":
    main()
