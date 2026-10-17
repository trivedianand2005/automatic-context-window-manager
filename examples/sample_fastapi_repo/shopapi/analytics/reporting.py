"""Sales reporting (batch job, not part of the request path)."""

from __future__ import annotations

from collections import Counter

from shopapi.utils.formatting import format_price, pluralize


def orders_per_product(orders: list[dict]) -> Counter:
    """Count units ordered per product id."""
    counts: Counter = Counter()
    for order in orders:
        counts[order["product_id"]] += order["quantity"]
    return counts


def revenue_cents(orders: list[dict], prices: dict[int, int]) -> int:
    """Total revenue; orders for unknown products are skipped and reported as errors."""
    total = 0
    for order in orders:
        price = prices.get(order["product_id"])
        if price is None:
            continue
        total += price * order["quantity"]
    return total


def report_errors(orders: list[dict], prices: dict[int, int]) -> list[str]:
    """Human-readable error lines for orders that reference unknown products."""
    errors = []
    for order in orders:
        if order["product_id"] not in prices:
            errors.append(f"order {order['id']}: unknown product {order['product_id']}")
    return errors


def summary_lines(orders: list[dict], prices: dict[int, int]) -> list[str]:
    lines = [
        f"Orders: {pluralize(len(orders), 'order')}",
        f"Revenue: {format_price(revenue_cents(orders, prices))}",
    ]
    for product_id, units in orders_per_product(orders).most_common(5):
        lines.append(f"  product {product_id}: {pluralize(units, 'unit')}")
    errors = report_errors(orders, prices)
    if errors:
        lines.append(f"Errors: {pluralize(len(errors), 'error')}")
        lines.extend(f"  {e}" for e in errors)
    return lines
