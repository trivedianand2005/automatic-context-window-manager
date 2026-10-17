"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    username: str
    full_name: str = ""


class Product(BaseModel):
    id: int
    name: str
    price_cents: int


class OrderCreate(BaseModel):
    # NOTE: no validation yet - quantity may be zero or negative.
    product_id: int
    quantity: int


class OrderOut(BaseModel):
    id: int
    product_id: int
    quantity: int
