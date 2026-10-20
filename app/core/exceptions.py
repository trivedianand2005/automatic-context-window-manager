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


class AuthenticationError(ACWMError):
    """Missing, invalid or expired credentials."""

    code = "not_authenticated"
    http_status = 401


class AccountExistsError(ACWMError):
    code = "account_exists"
    http_status = 409


class RateLimitedError(ACWMError):
    code = "rate_limited"
    http_status = 429


class NotFoundError(ACWMError):
    code = "not_found"
    http_status = 404


class QuotaExceededError(ACWMError):
    code = "quota_exceeded"
    http_status = 409


class NotConfiguredError(ACWMError):
    """An optional feature is not configured on this server."""

    code = "not_configured"
    http_status = 501
