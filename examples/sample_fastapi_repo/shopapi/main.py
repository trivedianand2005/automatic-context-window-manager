"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from shopapi.api.routes import auth, orders, public, users
from shopapi.core.config import get_settings
from shopapi.core.errors import register_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    register_exception_handlers(app)
    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(orders.router)
    app.include_router(users.router)
    return app


app = create_app()
