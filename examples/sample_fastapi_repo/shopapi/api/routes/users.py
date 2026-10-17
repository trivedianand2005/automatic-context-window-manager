"""User profile endpoints - require an authenticated user."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shopapi.api.dependencies import get_current_user
from shopapi.models.schemas import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(username=user["username"], full_name=user.get("full_name", ""))
