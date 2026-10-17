"""Generic retry helper with exponential backoff."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryExhaustedError(Exception):
    """Raised when every attempt failed."""

    def __init__(self, attempts: int, last_error: Exception) -> None:
        super().__init__(f"gave up after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def retry_with_backoff(
    operation: Callable[[], T],
    max_attempts: int,
    base_delay: float,
    retry_on: tuple[type[Exception], ...] = (ConnectionError,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``operation`` until it succeeds or ``max_attempts`` is reached.

    Known issue: the delay grows linearly (base_delay * attempt) instead of
    exponentially, and non-retryable errors are swallowed on the last attempt.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except retry_on as exc:
            last_error = exc
            if attempt < max_attempts:
                sleep(base_delay * attempt)
    assert last_error is not None
    raise RetryExhaustedError(max_attempts, last_error)
