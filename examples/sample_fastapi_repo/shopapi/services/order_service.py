"""Order business logic."""

from __future__ import annotations

from shopapi.db.database import Database
from shopapi.db.repositories import OrderRepository, ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.orders = OrderRepository(db)
        self.products = ProductRepository(db)

    def place_order(self, username: str, product_id: int, quantity: int) -> dict:
        return self.orders.create(username, product_id, quantity)

    def list_orders(self, username: str) -> list[dict]:
        return self.orders.for_user(username)

    def order_total_cents(self, order: dict) -> int:
        product = next(p for p in self.products.list(1000) if p["id"] == order["product_id"])
        return product["price_cents"] * order["quantity"]
