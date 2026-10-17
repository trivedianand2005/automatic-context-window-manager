"""FastAPI application factory.

Run with:  uvicorn app.api.main:app --reload --port 8000
Docs at:   http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.exceptions import ACWMError
from app.core.logging_config import configure_logging, get_logger
from app.services.acwm_service import ACWMService

log = get_logger("api")


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


class RequestSizeLimitMiddleware:
    """Pure ASGI middleware rejecting request bodies larger than ``max_bytes``."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            return await self._reject(send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await self._reject(send)

    async def _reject(self, send) -> None:
        response = _error(413, "request_too_large", f"Request body exceeds {self.max_bytes} bytes.")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": response.body})


class _BodyTooLarge(Exception):
    pass


def create_app(settings: Settings | None = None, service: ACWMService | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    app = FastAPI(
        title="Automatic Context Window Manager (ACWM)",
        version=__version__,
        description=(
            "Select dependency-aware, token-budgeted repository context for AI coding agents. "
            "Local developer tool: repositories must live under ACWM_ALLOWED_ROOTS. "
            "Repository code is parsed, never executed."
        ),
    )
    app.state.service = service or ACWMService(settings)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.api_max_request_bytes)

    @app.exception_handler(ACWMError)
    async def handle_acwm_error(request: Request, exc: ACWMError) -> JSONResponse:
        return _error(exc.http_status, exc.code, exc.message, exc.details or None)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return _error(422, "validation_error", "Request validation failed.", details)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s", request.url.path)
        return _error(500, "internal_error", "An unexpected error occurred.")

    app.include_router(router)
    return app


app = create_app()
