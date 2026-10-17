"""Seed the in-memory database with dummy demonstration data."""

from __future__ import annotations

from shopapi.db.database import get_database
from shopapi.db.repositories import ProductRepository
from shopapi.services.auth_service import AuthService

DEMO_PRODUCTS = [(1, "Demo Widget", 1999), (2, "Sample Gadget", 4999), (3, "Test Gizmo", 999)]


def seed() -> None:
    db = get_database()
    products = ProductRepository(db)
    for product_id, name, price in DEMO_PRODUCTS:
        products.add(product_id, name, price)
    AuthService(db).register("demo", "demo-password", "Demo User")


if __name__ == "__main__":
    seed()
    print("Seeded demo data.")
