import pytest

from shopapi.utils.retry import RetryExhaustedError, retry_with_backoff


def test_retry_returns_first_success():
    calls = []

    def op():
        calls.append(1)
        if len(calls) < 2:
            raise ConnectionError("boom")
        return "ok"

    assert retry_with_backoff(op, max_attempts=3, base_delay=0, sleep=lambda _: None) == "ok"
    assert len(calls) == 2


def test_retry_raises_when_exhausted():
    def op():
        raise ConnectionError("down")

    with pytest.raises(RetryExhaustedError):
        retry_with_backoff(op, max_attempts=2, base_delay=0, sleep=lambda _: None)
