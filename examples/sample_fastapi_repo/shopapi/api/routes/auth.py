"""Login/logout endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from shopapi.api.dependencies import get_auth_service
from shopapi.models.schemas import LoginRequest, TokenResponse
from shopapi.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, auth: AuthService = Depends(get_auth_service)) -> TokenResponse:
    user = auth.authenticate(body.username, body.password)
    token, ttl = auth.issue_token(user["username"])
    return TokenResponse(access_token=token, expires_in=ttl)


@router.post("/logout", status_code=204)
def logout(
    authorization: str = Header(...), auth: AuthService = Depends(get_auth_service)
) -> None:
    auth.logout(authorization.split(" ", 1)[-1])
