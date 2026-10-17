"""Order endpoints - require an authenticated user."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shopapi.api.dependencies import get_current_user, get_order_service
from shopapi.models.schemas import OrderCreate, OrderOut
from shopapi.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
def my_orders(
    user: dict = Depends(get_current_user), orders: OrderService = Depends(get_order_service)
) -> list[dict]:
    return orders.list_orders(user["username"])


@router.post("", response_model=OrderOut, status_code=201)
def place_order(
    body: OrderCreate,
    user: dict = Depends(get_current_user),
    orders: OrderService = Depends(get_order_service),
) -> dict:
    return orders.place_order(user["username"], body.product_id, body.quantity)
