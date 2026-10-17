"""TinyFish Search API adapter (optional documentation research).

Documented API (verified against https://docs.tinyfish.ai/search-api/reference on
2026-10-17, see docs/tinyfish_integration.md):

    GET https://api.search.tinyfish.ai?query=...&include_domains=a.com,b.com
    Header: X-API-Key: <TINYFISH_API_KEY>
    200 -> {"query": str, "results": [{"position", "site_name", "title", "snippet",
            "url", ...}], "total_results": int, "page": int}
    Errors: 400, 401, 402, 403, 404, 429 (rate limit; default 30 req/min), 500, 503

Retrieved snippets are external, untrusted text: they are length-limited, stripped of
control characters, shown with source URLs, and only included in a context package
when the user opts in. They are never executed or treated as instructions.

The live service has NOT been called from this repository (no credentials available
during development); behaviour is covered by tests with mocked HTTP responses.
"""

from __future__ import annotations

import os
import re
import time

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.logging_config import get_logger
from app.integrations.mock_web_research import MockWebResearch
from app.integrations.research_models import ResearchFinding, ResearchResult

log = get_logger("tinyfish")
SEARCH_URL = "https://api.search.tinyfish.ai"
MAX_SNIPPET_CHARS = 400
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class _SearchItem(BaseModel):
    position: int | None = None
    site_name: str | None = None
    title: str = ""
    snippet: str = ""
    url: str


class _SearchResponse(BaseModel):
    query: str = ""
    results: list[_SearchItem] = Field(default_factory=list)
    total_results: int | None = None
    page: int | None = None


def _clean(text: str, limit: int) -> str:
    text = _CONTROL.sub(" ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


class TinyFishSearchClient:
    name = "tinyfish"

    def __init__(
        self,
        api_key: str | None,
        include_domains: list[str],
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 1,
    ) -> None:
        self._api_key = api_key
        self.include_domains = include_domains
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport
        self.available = bool(api_key)
        self.status = (
            "real: TinyFish Search API configured (unverified until a request succeeds)"
            if self.available
            else "unconfigured (set TINYFISH_API_KEY)"
        )

    def _request(self, params: dict) -> httpx.Response:
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            return client.get(
                SEARCH_URL,
                params=params,
                headers={"X-API-Key": self._api_key or "", "Accept": "application/json"},
            )

    def research(self, task: str, terms: list[str], max_results: int = 5) -> ResearchResult:
        query = " ".join(dict.fromkeys(terms[:8])) or task[:200]
        if not self.available:
            return ResearchResult(
                provider="tinyfish",
                status=self.status,
                query=query,
                error="TinyFish API key not configured",
            )
        params = {
            "query": query[:500],
            "purpose": "Find official technical documentation relevant to a coding task.",
        }
        if self.include_domains:
            params["include_domains"] = ",".join(self.include_domains)
        attempt = 0
        while True:
            try:
                response = self._request(params)
            except httpx.TimeoutException:
                return self._failure(query, "TinyFish request timed out")
            except httpx.HTTPError as exc:
                return self._failure(query, f"TinyFish connection error ({type(exc).__name__})")
            if response.status_code in (429, 503) and attempt < self.max_retries:
                retry_after = response.headers.get("retry-after", "2")
                delay = min(float(retry_after) if retry_after.isdigit() else 2.0, 10.0)
                attempt += 1
                time.sleep(delay)
                continue
            break
        if response.status_code != 200:
            messages = {
                400: "invalid request",
                401: "missing or invalid API key",
                402: "out of credits",
                403: "forbidden",
                404: "Search API not available",
                429: "rate limit exceeded",
                500: "TinyFish internal error",
                503: "service unavailable",
            }
            return self._failure(
                query,
                f"TinyFish HTTP {response.status_code}: "
                f"{messages.get(response.status_code, 'unexpected status')}",
            )
        try:
            payload = _SearchResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            return self._failure(query, "TinyFish returned an unexpected response format")
        findings = [
            ResearchFinding(
                title=_clean(item.title, 200) or item.url,
                url=item.url,
                snippet=_clean(item.snippet, MAX_SNIPPET_CHARS),
                source=f"TinyFish Search API ({item.site_name or 'web'})",
            )
            for item in payload.results
            if item.url.startswith(("https://", "http://"))
        ][:max_results]
        self.status = "real: TinyFish Search API (last request succeeded)"
        return ResearchResult(
            provider="tinyfish", status=self.status, query=query, findings=findings
        )

    def _failure(self, query: str, message: str) -> ResearchResult:
        log.warning("TinyFish research failed: %s", message)
        return ResearchResult(
            provider="tinyfish", status=f"error: {message}", query=query, error=message
        )


def get_research_provider(
    enabled: bool,
    include_domains: list[str],
    timeout: float,
    use_mock_when_unconfigured: bool = True,
):
    """Return the real client when enabled+configured, else the mock (or None)."""
    if not enabled:
        return None
    api_key = os.getenv("TINYFISH_API_KEY")
    if api_key:
        return TinyFishSearchClient(api_key, include_domains, timeout)
    return MockWebResearch() if use_mock_when_unconfigured else None


def provider_status(enabled: bool) -> str:
    if not enabled:
        return "disabled"
    if os.getenv("TINYFISH_API_KEY"):
        return "real (configured; unverified until a request succeeds)"
    return "mock (TINYFISH_API_KEY not set; canned offline results)"
