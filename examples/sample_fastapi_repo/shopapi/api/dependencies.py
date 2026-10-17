"""FastAPI dependencies shared by routers."""

from __future__ import annotations

from fastapi import Depends, Header

from shopapi.core.errors import AuthenticationError
from shopapi.db.database import Database, get_database
from shopapi.services.auth_service import AuthService
from shopapi.services.order_service import OrderService


def get_db() -> Database:
    return get_database()


def get_auth_service(db: Database = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_order_service(db: Database = Depends(get_db)) -> OrderService:
    return OrderService(db)


def get_current_user(
    authorization: str | None = Header(default=None),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Resolve the bearer session token in the Authorization header to a user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("missing bearer token")
    return auth.resolve_token(authorization.split(" ", 1)[1].strip())
