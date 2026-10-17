"""Logging setup with a redaction filter so credentials never reach log output."""

from __future__ import annotations

import logging

from app.utils.security import redact_secrets


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            record.args = tuple(redact_secrets(a) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger("acwm")
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"acwm.{name}")
