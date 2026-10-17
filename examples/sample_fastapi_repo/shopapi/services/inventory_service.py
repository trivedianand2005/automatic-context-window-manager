"""Inventory reservations for products (not yet exposed through the API)."""

from __future__ import annotations

from collections import defaultdict


class OutOfStockError(Exception):
    pass


class InventoryService:
    def __init__(self) -> None:
        self.stock: dict[int, int] = defaultdict(int)
        self.reserved: dict[int, int] = defaultdict(int)

    def restock(self, product_id: int, quantity: int) -> int:
        if quantity <= 0:
            raise ValueError("restock quantity must be positive")
        self.stock[product_id] += quantity
        return self.available(product_id)

    def available(self, product_id: int) -> int:
        return self.stock[product_id] - self.reserved[product_id]

    def reserve(self, product_id: int, quantity: int) -> None:
        if quantity > self.available(product_id):
            raise OutOfStockError(f"only {self.available(product_id)} left of {product_id}")
        self.reserved[product_id] += quantity

    def release(self, product_id: int, quantity: int) -> None:
        self.reserved[product_id] = max(0, self.reserved[product_id] - quantity)

    def commit(self, product_id: int, quantity: int) -> None:
        self.release(product_id, quantity)
        self.stock[product_id] -= quantity
