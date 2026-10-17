"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shopapi.core.config import Settings
from shopapi.db.database import reset_database
from shopapi.db.repositories import ProductRepository
from shopapi.main import create_app
from shopapi.services.auth_service import AuthService


@pytest.fixture()
def db():
    database = reset_database(Settings(database_url="memory://test"))
    ProductRepository(database).add(1, "Demo Widget", 1999)
    return database


@pytest.fixture()
def client(db):
    return TestClient(create_app())


@pytest.fixture()
def demo_user(db):
    AuthService(db).register("demo", "demo-password", "Demo User")
    return {"username": "demo", "password": "demo-password"}


@pytest.fixture()
def auth_headers(client, demo_user):
    response = client.post("/auth/login", json=demo_user)
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
