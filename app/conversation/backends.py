"""Chat backends shared by the manager model and the main (answering) model.

Every backend returns an ``LLMResult`` with the text plus token usage and latency, and
raises ``ProviderError`` for any failure (timeout, HTTP error, refusal, bad response).
Callers decide what a failure means; the conversation manager falls back to heuristics.

    anthropic  Anthropic Messages API via the official SDK (ANTHROPIC_API_KEY from env)
    ollama     local model through Ollama's /api/chat endpoint
    mock       scripted or callable responses, for tests and --dry-run (no network)
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.conversation.config import ConversationConfig, ModelSettings
from app.core.exceptions import ProviderError
from app.core.logging_config import get_logger

log = get_logger("conversation.backends")
MOCK_CHARS_PER_TOKEN = 4.0


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class LLMBackend(Protocol):
    name: str
    model: str
    available: bool

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult: ...


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        self.model = settings.model
        self._client = None
        self.available = importlib.util.find_spec("anthropic") is not None and bool(
            os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        )

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(timeout=self.settings.timeout_seconds, max_retries=1)
        return self._client

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        if not self.available:
            raise ProviderError("Anthropic backend is not configured (set ANTHROPIC_API_KEY).")
        import anthropic

        output_config: dict = {}
        if self.settings.effort:
            output_config["effort"] = self.settings.effort
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens or self.settings.max_tokens,
            "system": system,
            "messages": messages,
        }
        if output_config:
            kwargs["output_config"] = output_config
        start = time.perf_counter()
        try:
            client = self._get_client()
            if self.settings.refusal_fallbacks:
                response = client.beta.messages.create(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = client.messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            raise ProviderError("LLM rate limit exceeded.") from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderError("LLM request timed out.") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"LLM API error (HTTP {exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Could not connect to the LLM API.") from exc
        latency = (time.perf_counter() - start) * 1000
        if response.stop_reason == "refusal":
            raise ProviderError("The model declined this request.")
        text = "".join(b.text for b in response.content if b.type == "text")
        return LLMResult(
            text=text,
            model=response.model or self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency,
        )


class OllamaBackend:
    name = "ollama"

    def __init__(self, settings: ModelSettings, host: str, model: str, temperature: float) -> None:
        self.settings = settings
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        # Reachability is only known once a request is made.
        self.available = True

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens or self.settings.max_tokens,
            },
        }
        if json_schema is not None:
            body["format"] = json_schema
        start = time.perf_counter()
        try:
            resp = httpx.post(
                f"{self.host}/api/chat", json=body, timeout=self.settings.timeout_seconds
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            raise ProviderError("Ollama request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"Ollama error (HTTP {exc.response.status_code}).") from exc
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Could not reach Ollama at {self.host}.") from exc
        latency = (time.perf_counter() - start) * 1000
        text = (data.get("message") or {}).get("content", "")
        return LLMResult(
            text=text,
            model=self.model,
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
            latency_ms=latency,
        )


Responder = Callable[[str, list[dict]], str]


class MockBackend:
    """Deterministic backend. ``responses`` is a list (returned in order) or a callable.

    A response that is an Exception instance is raised instead of returned, which lets
    tests simulate timeouts and API errors.
    """

    name = "mock"
    available = True

    def __init__(self, responses: list[str | Exception] | Responder, model: str = "mock") -> None:
        self.model = model
        self._responses = responses
        self.calls: list[tuple[str, list[dict]]] = []

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        self.calls.append((system, messages))
        start = time.perf_counter()
        if callable(self._responses):
            out: str | Exception = self._responses(system, messages)
        elif self._responses:
            out = self._responses.pop(0)
        else:
            out = ProviderError("Mock backend has no responses left.")
        if isinstance(out, Exception):
            raise out
        prompt_chars = len(system) + sum(len(str(m.get("content", ""))) for m in messages)
        return LLMResult(
            text=out,
            model=self.model,
            input_tokens=math.ceil(prompt_chars / MOCK_CHARS_PER_TOKEN),
            output_tokens=math.ceil(len(out) / MOCK_CHARS_PER_TOKEN),
            latency_ms=(time.perf_counter() - start) * 1000,
        )


def build_backend(
    role: str, cfg: ConversationConfig, mock: MockBackend | None = None
) -> LLMBackend | None:
    """Backend for ``role`` ("manager" or "main_model"); ``None`` means heuristics only."""
    settings: ModelSettings = getattr(cfg, role)
    if settings.backend == "none":
        return None
    if settings.backend == "mock":
        return mock or MockBackend(lambda _s, _m: "", model="mock")
    if settings.backend == "ollama":
        model = cfg.ollama.manager_model if role == "manager" else cfg.ollama.main_model
        return OllamaBackend(settings, cfg.ollama.host, model, cfg.ollama.temperature)
    backend = AnthropicBackend(settings)
    if not backend.available:
        log.warning("%s: Anthropic backend unavailable (no API key); falling back.", role)
        return None
    return backend
