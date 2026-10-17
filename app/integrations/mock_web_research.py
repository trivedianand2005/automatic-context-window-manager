"""Offline mock documentation-research provider (for demos and tests).

Results are canned, clearly labelled MOCK, and are *not* fetched from the web.
"""

from __future__ import annotations

from app.integrations.research_models import ResearchFinding, ResearchResult

_CANNED = [
    (
        {"jwt", "auth", "authentication", "token", "oauth2", "login", "protected"},
        "FastAPI - Security: OAuth2 with Password (and hashing), Bearer with JWT tokens",
        "https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/",
        "Tutorial covering OAuth2PasswordBearer, creating and verifying JWT access tokens and "
        "protecting path operations with dependencies.",
    ),
    (
        {"dependency", "depends", "protected", "route", "auth"},
        "FastAPI - Dependencies",
        "https://fastapi.tiangolo.com/tutorial/dependencies/",
        "How Depends() injects shared logic such as the current user into path operations.",
    ),
    (
        {"test", "tests", "testing", "pytest", "testclient"},
        "FastAPI - Testing",
        "https://fastapi.tiangolo.com/tutorial/testing/",
        "Using TestClient with pytest, and overriding dependencies in tests.",
    ),
    (
        {"error", "errors", "exception", "handling", "handler"},
        "FastAPI - Handling Errors",
        "https://fastapi.tiangolo.com/tutorial/handling-errors/",
        "HTTPException, custom exception handlers and overriding default validation errors.",
    ),
    (
        {"validation", "validate", "request", "pydantic", "schema"},
        "Pydantic - Validators",
        "https://docs.pydantic.dev/latest/concepts/validators/",
        "Field and model validators for request/response validation.",
    ),
    (
        {"config", "settings", "env", "configuration"},
        "FastAPI - Settings and Environment Variables",
        "https://fastapi.tiangolo.com/advanced/settings/",
        "Reading configuration from environment variables with Pydantic settings.",
    ),
]


class MockWebResearch:
    name = "mock"
    available = True
    status = "mock (offline canned results; not real web research)"

    def research(self, task: str, terms: list[str], max_results: int = 5) -> ResearchResult:
        lowered = {t.lower() for t in terms} | set(task.lower().split())
        findings = [
            ResearchFinding(
                title=title, url=url, snippet=snippet, source="ACWM mock research (canned)"
            )
            for keys, title, url, snippet in _CANNED
            if keys & lowered
        ][:max_results]
        return ResearchResult(
            provider="mock", status=self.status, findings=findings, query=" ".join(terms[:8])
        )
