"""Public (unauthenticated) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shopapi.api.dependencies import get_db
from shopapi.core.config import get_settings
from shopapi.db.database import Database
from shopapi.db.repositories import ProductRepository
from shopapi.models.schemas import Product

router = APIRouter(tags=["public"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": get_settings().app_name}


@router.get("/products", response_model=list[Product])
def list_products(limit: int = 20, db: Database = Depends(get_db)) -> list[dict]:
    limit = min(limit, get_settings().page_size_limit)
    return ProductRepository(db).list(limit)
