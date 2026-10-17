"""Data-access repositories built on the in-memory Database."""

from __future__ import annotations

import itertools

from shopapi.core.errors import NotFoundError
from shopapi.db.database import Database


class UserRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, username: str, password_hash: str, full_name: str = "") -> dict:
        users = self.db.table("users")
        user = {"username": username, "password_hash": password_hash, "full_name": full_name}
        users[username] = user
        return user

    def get(self, username: str) -> dict | None:
        return self.db.table("users").get(username)


class SessionRepository:
    """Server-side storage for opaque session tokens."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, token: str, username: str, expires_at: float) -> None:
        self.db.table("sessions")[token] = {"username": username, "expires_at": expires_at}

    def get(self, token: str) -> dict | None:
        return self.db.table("sessions").get(token)

    def delete(self, token: str) -> None:
        self.db.table("sessions").pop(token, None)


class ProductRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self, limit: int = 20) -> list[dict]:
        return list(self.db.table("products").values())[:limit]

    def add(self, product_id: int, name: str, price_cents: int) -> dict:
        product = {"id": product_id, "name": name, "price_cents": price_cents}
        self.db.table("products")[product_id] = product
        return product


class OrderRepository:
    _ids = itertools.count(1)

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, username: str, product_id: int, quantity: int) -> dict:
        if product_id not in self.db.table("products"):
            raise NotFoundError(f"product {product_id} not found")
        order = {"id": next(self._ids), "username": username, "product_id": product_id,
                 "quantity": quantity}
        self.db.table("orders")[order["id"]] = order
        return order

    def for_user(self, username: str) -> list[dict]:
        return [o for o in self.db.table("orders").values() if o["username"] == username]
