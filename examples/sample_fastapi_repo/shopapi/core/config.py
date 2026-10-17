"""Application settings loaded from environment variables.

All defaults are safe demonstration values. Real deployments must set
SHOPAPI_SECRET_KEY and SHOPAPI_DATABASE_URL explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "ShopAPI"
    environment: str = field(default_factory=lambda: os.getenv("SHOPAPI_ENV", "development"))
    # Used to sign session tokens. Placeholder only - never use in production.
    secret_key: str = field(
        default_factory=lambda: os.getenv("SHOPAPI_SECRET_KEY", "dev-only-placeholder")
    )
    access_token_ttl_minutes: int = field(
        default_factory=lambda: _env_int("SHOPAPI_TOKEN_TTL_MINUTES", 30)
    )
    database_url: str = field(
        default_factory=lambda: os.getenv("SHOPAPI_DATABASE_URL", "memory://shopapi")
    )
    db_max_retries: int = field(default_factory=lambda: _env_int("SHOPAPI_DB_MAX_RETRIES", 3))
    db_retry_base_delay: float = 0.05
    page_size_limit: int = 100


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
