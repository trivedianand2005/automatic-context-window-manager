import httpx

from app.analysis.task_analyzer import analyze_task_with_llm
from app.context.summarizer import SUMMARY_HEADER, llm_summary
from app.context.token_counter import get_token_counter
from app.core.exceptions import ProviderError
from app.core.models import RepoFile
from app.integrations.llm_provider import AnthropicProvider, NullProvider, get_llm_provider
from app.integrations.mock_web_research import MockWebResearch
from app.integrations.tinyfish_client import (
    SEARCH_URL,
    TinyFishSearchClient,
    get_research_provider,
    provider_status,
)

SEARCH_OK = {
    "query": "fastapi jwt",
    "results": [
        {
            "position": 1,
            "site_name": "fastapi.tiangolo.com",
            "title": "OAuth2 with JWT",
            "snippet": "Use \x00 OAuth2PasswordBearer " + "x" * 600,
            "url": "https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/",
        },
        {
            "position": 2,
            "site_name": "evil",
            "title": "bad",
            "snippet": "s",
            "url": "javascript:alert(1)",
        },
    ],
    "total_results": 2,
    "page": 0,
}


def client_with(handler, **kw):
    return TinyFishSearchClient(
        "test-key",
        ["fastapi.tiangolo.com"],
        timeout=1,
        transport=httpx.MockTransport(handler),
        **kw,
    )


def test_tinyfish_success_request_format_and_sanitising():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key")
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=SEARCH_OK)

    res = client_with(handler).research("Add JWT auth", ["fastapi", "jwt"])
    assert seen["url"].startswith(SEARCH_URL)
    assert seen["key"] == "test-key"
    assert seen["params"]["query"] == "fastapi jwt"
    assert seen["params"]["include_domains"] == "fastapi.tiangolo.com"
    assert res.error is None and res.provider == "tinyfish"
    assert len(res.findings) == 1  # non-http URL dropped
    f = res.findings[0]
    assert "\x00" not in f.snippet and len(f.snippet) <= 400
    assert f.url.startswith("https://fastapi.tiangolo.com")
    assert "last request succeeded" in res.status


def test_tinyfish_auth_error_and_malformed_response():
    res = client_with(lambda r: httpx.Response(401, json={"error": "INVALID_API_KEY"})).research(
        "t", ["a"]
    )
    assert res.error and "401" in res.error and not res.findings
    res = client_with(lambda r: httpx.Response(200, text="not json")).research("t", ["a"])
    assert "unexpected response" in res.error


def test_tinyfish_rate_limit_retry(monkeypatch):
    monkeypatch.setattr("app.integrations.tinyfish_client.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json=SEARCH_OK)

    res = client_with(handler).research("t", ["a"])
    assert len(calls) == 2 and res.findings
    res = client_with(lambda r: httpx.Response(429), max_retries=0).research("t", ["a"])
    assert "rate limit" in res.error


def test_tinyfish_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    assert "timed out" in client_with(handler).research("t", ["a"]).error


def test_tinyfish_unconfigured_and_provider_selection(monkeypatch):
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    res = TinyFishSearchClient(None, []).research("t", ["a"])
    assert res.error and "not configured" in res.error
    assert get_research_provider(False, [], 1) is None
    assert isinstance(get_research_provider(True, [], 1), MockWebResearch)
    assert provider_status(True).startswith("mock")
    monkeypatch.setenv("TINYFISH_API_KEY", "k")
    assert isinstance(get_research_provider(True, [], 1), TinyFishSearchClient)
    assert "unverified" in provider_status(True)


def test_mock_research_is_labelled():
    res = MockWebResearch().research("Add JWT authentication", ["jwt", "auth"])
    assert res.provider == "mock" and res.findings
    assert all("mock" in f.source.lower() for f in res.findings)


class FakeLLM:
    name = "fake"
    available = True
    status = "fake"

    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.prompts = reply, fail, []

    def complete(self, prompt, max_tokens=512):
        self.prompts.append(prompt)
        if self.fail:
            raise ProviderError("boom")
        return self.reply


def test_llm_task_analysis_augments_and_falls_back():
    llm = FakeLLM(reply='["OAuth2PasswordBearer", "python-jose", "bad term!!", 5]')
    a = analyze_task_with_llm("Add JWT auth", llm)
    assert "oauth2passwordbearer" in a.expanded_terms and a.analyzer.startswith("deterministic+")
    assert "<task>" in llm.prompts[0] and "untrusted" in llm.prompts[0]
    b = analyze_task_with_llm("Add JWT auth", FakeLLM(fail=True))
    assert b.analyzer == "deterministic" and any("fallback" in n for n in b.notes)


def test_llm_summary_labelled_and_fallback():
    f = RepoFile(
        path="a.py",
        language="python",
        file_type="source",
        size_bytes=10,
        sha256="h",
        tokens=5,
        content="def a():\n    return 1\n",
        line_count=2,
    )
    counter = get_token_counter()
    ex = llm_summary(f, "task", FakeLLM(reply="Defines a() returning 1."), counter)
    assert ex.kind == "summary" and ex.content.startswith(SUMMARY_HEADER)
    assert llm_summary(f, "task", FakeLLM(fail=True), counter) is None
    assert llm_summary(f, "task", NullProvider(), counter) is None


def test_provider_factory_and_unconfigured_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert isinstance(get_llm_provider("none", "m", 5), NullProvider)
    assert isinstance(get_llm_provider("unknown", "m", 5), NullProvider)
    p = get_llm_provider("anthropic", "claude-opus-5-5", 5)
    assert isinstance(p, AnthropicProvider) and not p.available
    assert "unconfigured" in p.status


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Response:
    def __init__(self, text, stop_reason="end_turn"):
        self.content, self.stop_reason = [_Block(text)], stop_reason


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.calls = []
        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                if error is not None:
                    raise error
                return response

        class _Beta:
            messages = _Messages()

        self.beta = _Beta()


def _provider(monkeypatch, client):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    p = AnthropicProvider(model="claude-opus-5-5", timeout=5)
    if not p.available:  # anthropic SDK not installed
        import pytest

        pytest.skip("anthropic SDK not installed")
    p._client = client
    return p


def test_anthropic_provider_success_and_request_shape(monkeypatch):
    client = _FakeClient(response=_Response("summary text"))
    p = _provider(monkeypatch, client)
    assert p.complete("prompt", max_tokens=100) == "summary text"
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["max_tokens"] == 100
    assert "untrusted" in call["system"]
    assert call["messages"] == [{"role": "user", "content": "prompt"}]
    assert "last request succeeded" in p.status


def test_anthropic_provider_refusal_and_errors(monkeypatch):
    import anthropic
    import httpx as _httpx
    import pytest

    p = _provider(monkeypatch, _FakeClient(response=_Response("", stop_reason="refusal")))
    with pytest.raises(ProviderError, match="declined"):
        p.complete("x")
    request = _httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIConnectionError(request=request)
    p = _provider(monkeypatch, _FakeClient(error=err))
    with pytest.raises(ProviderError, match="connect"):
        p.complete("x")
