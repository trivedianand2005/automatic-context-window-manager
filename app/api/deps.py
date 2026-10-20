"""Request dependencies: who is calling, and which ACWMService instance serves them."""

from __future__ import annotations

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError
from app.services.accounts import AccountService, PublicUser
from app.services.acwm_service import ACWMService

SESSION_HEADER = "X-ACWM-Session"
bearer = HTTPBearer(auto_error=False, description="Login token from /auth/login or /auth/signup")


def get_accounts(request: Request) -> AccountService:
    return request.app.state.accounts


def optional_user(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> PublicUser | None:
    """The logged-in user, or None. An invalid or expired token is an error, not anonymous."""
    if creds is None:
        return None
    return request.app.state.accounts.user_from_token(creds.credentials)


def require_user(user: PublicUser | None = Depends(optional_user)) -> PublicUser:
    if user is None:
        raise AuthenticationError("Please log in first.")
    return user


def _service_for(request: Request, user: PublicUser | None, session_id: str | None) -> ACWMService:
    if user is not None:
        # Each account gets its own isolated service (indexes, run history).
        return request.app.state.sessions.get(f"user-{user.id:08d}")
    if session_id:
        return request.app.state.sessions.get(session_id)
    return request.app.state.service


def get_service(
    request: Request,
    session_id: str | None = Header(None, alias=SESSION_HEADER, max_length=64),
    user: PublicUser | None = Depends(optional_user),
) -> ACWMService:
    """Service for working endpoints. Requires login when ACWM_REQUIRE_AUTH is on."""
    if user is None and request.app.state.service.settings.require_auth:
        raise AuthenticationError("Please log in to use ACWM.")
    return _service_for(request, user, session_id)


def get_public_service(
    request: Request,
    session_id: str | None = Header(None, alias=SESSION_HEADER, max_length=64),
    user: PublicUser | None = Depends(optional_user),
) -> ACWMService:
    """Service for public endpoints (health, config); never requires login."""
    return _service_for(request, user, session_id)


def client_ip(request: Request) -> str:
    # Render (and most hosts) put the original client first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"
