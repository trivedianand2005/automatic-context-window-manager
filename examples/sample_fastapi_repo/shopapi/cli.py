"""Small admin command-line interface (dummy data only)."""

from __future__ import annotations

import argparse

from shopapi.analytics.reporting import summary_lines
from shopapi.db.database import get_database
from shopapi.db.repositories import ProductRepository


def cmd_products(args: argparse.Namespace) -> None:
    for product in ProductRepository(get_database()).list(args.limit):
        print(f"{product['id']:>4}  {product['name']:<20} {product['price_cents']:>8}")


def cmd_report(args: argparse.Namespace) -> None:
    db = get_database()
    prices = {p["id"]: p["price_cents"] for p in ProductRepository(db).list(1000)}
    orders = list(db.table("orders").values())
    print("\n".join(summary_lines(orders, prices)))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="shopapi")
    sub = parser.add_subparsers(dest="command", required=True)
    products = sub.add_parser("products", help="list products")
    products.add_argument("--limit", type=int, default=20)
    products.set_defaults(func=cmd_products)
    report = sub.add_parser("report", help="print sales report")
    report.set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
