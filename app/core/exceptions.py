"""Domain exceptions. Messages must never contain secret values or file contents."""

from __future__ import annotations


class ACWMError(Exception):
    """Base class for all ACWM errors."""

    code = "acwm_error"
    http_status = 400

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PathSecurityError(ACWMError):
    code = "path_not_allowed"
    http_status = 403


class RepositoryNotFoundError(ACWMError):
    code = "repository_not_found"
    http_status = 404


class InvalidRepositoryError(ACWMError):
    code = "invalid_repository"
    http_status = 400


class BudgetExceededError(ACWMError):
    code = "budget_exceeded"
    http_status = 422


class IndexingLimitError(ACWMError):
    code = "indexing_limit"
    http_status = 413


class ProviderError(ACWMError):
    """An optional external provider (LLM, TinyFish) failed."""

    code = "provider_error"
    http_status = 502
