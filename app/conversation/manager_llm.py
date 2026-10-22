"""The manager LLM: a small, cheap model used ONLY for context management.

It summarizes, scores and extracts facts from older messages. It never answers the user.
Any backend failure, timeout or invalid response yields ``output=None`` so the caller
can fall back to heuristics; this class never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.conversation.backends import LLMBackend, LLMResult
from app.conversation.models import MANAGER_OUTPUT_SCHEMA, Fact, ManagerOutput, Message
from app.conversation.prompts import (
    COMPACTION_PROMPT,
    MANAGER_SYSTEM,
    REPAIR_PROMPT,
    render_message,
)
from app.conversation.structured import InvalidManagerOutput, parse_manager_output
from app.core.logging_config import get_logger

log = get_logger("conversation.manager_llm")
MAX_REPAIR_REPLY_CHARS = 4000


@dataclass
class ManagerCall:
    output: ManagerOutput | None
    results: list[LLMResult] = field(default_factory=list)
    error: str | None = None

    @property
    def input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.results)

    @property
    def output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.results)

    @property
    def latency_ms(self) -> float:
        return sum(r.latency_ms for r in self.results)


class ManagerLLM:
    def __init__(self, backend: LLMBackend, json_retries: int = 1, summary_words: int = 250):
        self.backend = backend
        self.json_retries = json_retries
        self.summary_words = summary_words

    @property
    def model(self) -> str:
        return self.backend.model

    def build_prompt(self, messages: list[Message], summary: str, facts: list[Fact]) -> str:
        return COMPACTION_PROMPT.format(
            previous_summary=summary or "(none)",
            existing_facts="\n".join(f"- {f.text}" for f in facts) or "(none)",
            messages="\n\n".join(render_message(m.id, m.role, m.turn, m.content) for m in messages),
            summary_words=self.summary_words,
        )

    def compact(self, messages: list[Message], summary: str, facts: list[Fact]) -> ManagerCall:
        prompt = self.build_prompt(messages, summary, facts)
        call = ManagerCall(output=None)
        content = prompt
        for attempt in range(self.json_retries + 1):
            try:
                result = self.backend.complete(
                    MANAGER_SYSTEM,
                    [{"role": "user", "content": content}],
                    json_schema=MANAGER_OUTPUT_SCHEMA,
                )
            except Exception as exc:  # noqa: BLE001 - the manager must never crash ACWM
                call.error = f"manager call failed: {exc}"
                log.warning("Manager LLM failed (%s); using heuristics.", exc)
                return call
            call.results.append(result)
            try:
                call.output = parse_manager_output(result.text)
                return call
            except InvalidManagerOutput as exc:
                call.error = f"invalid manager output: {exc}"
                log.warning("Manager LLM output invalid on attempt %d: %s", attempt + 1, exc)
                content = prompt + REPAIR_PROMPT.format(
                    error=exc, reply=result.text[:MAX_REPAIR_REPLY_CHARS]
                )
        log.warning("Manager LLM output still invalid after retries; using heuristics.")
        return call
