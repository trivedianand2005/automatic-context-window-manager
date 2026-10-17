"""Domain exceptions and FastAPI exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ShopAPIError(Exception):
    status_code = 400
    code = "shopapi_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ShopAPIError):
    status_code = 404
    code = "not_found"


class AuthenticationError(ShopAPIError):
    status_code = 401
    code = "not_authenticated"


class DatabaseUnavailableError(ShopAPIError):
    status_code = 503
    code = "database_unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    """Translate domain errors into consistent JSON error bodies."""

    @app.exception_handler(ShopAPIError)
    async def handle_shopapi_error(request: Request, exc: ShopAPIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
