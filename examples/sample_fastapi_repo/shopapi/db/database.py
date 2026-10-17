"""Tiny in-memory database abstraction with connection retry behaviour.

``memory://`` URLs never fail. ``flaky://N`` URLs fail the first N connection
attempts, which lets tests exercise the retry logic.
"""

from __future__ import annotations

from typing import Any

from shopapi.core.config import Settings, get_settings
from shopapi.core.errors import DatabaseUnavailableError
from shopapi.utils.retry import RetryExhaustedError, retry_with_backoff


class Database:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tables: dict[str, dict[Any, dict]] = {}
        self._connected = False
        self._failures_remaining = self._parse_flaky(self.settings.database_url)
        self.connection_attempts = 0

    @staticmethod
    def _parse_flaky(url: str) -> int:
        if url.startswith("flaky://"):
            try:
                return int(url.removeprefix("flaky://"))
            except ValueError:
                return 0
        return 0

    def _connect_once(self) -> None:
        self.connection_attempts += 1
        if self._failures_remaining > 0:
            self._failures_remaining -= 1
            raise ConnectionError("simulated transient connection failure")
        self._connected = True

    def connect(self) -> None:
        """Connect, retrying transient failures according to settings."""
        try:
            retry_with_backoff(
                self._connect_once,
                max_attempts=self.settings.db_max_retries,
                base_delay=self.settings.db_retry_base_delay,
            )
        except RetryExhaustedError as exc:
            raise DatabaseUnavailableError("database connection failed") from exc

    def table(self, name: str) -> dict[Any, dict]:
        if not self._connected:
            self.connect()
        return self._tables.setdefault(name, {})


_db: Database | None = None


def get_database() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def reset_database(settings: Settings | None = None) -> Database:
    global _db
    _db = Database(settings)
    return _db
