"""Hybrid conversation context manager.

Every turn (cheap, no LLM): count tokens and track per-message metadata.

Past a threshold (default 75% of the budget) the manager LLM compacts the context:

1. The system prompt and the most recent N turns stay verbatim; pinned messages too.
2. Older, unpinned messages go to the manager LLM, which returns a running summary,
   pinned facts, per-message scores (1-5) and superseded message ids.
3. They are replaced by a pinned-facts block (never evicted), the running summary and
   any messages scored >= ``verbatim_min_score`` (minus superseded ones).
4. If usage is still above the target (default 50%), the lowest-scored old messages are
   evicted (ties: oldest first).

Hysteresis: the gap between threshold and target leaves room for several turns before
the next trigger, and ``cooldown_turns`` stops back-to-back manager calls when the recent
turns alone keep usage high. If the context would overflow during a cooldown, a
heuristic-only compaction (no LLM) runs instead. Any manager failure falls back to the
same heuristics, so a failing manager never breaks a turn.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass

from app.context.token_counter import TokenCounter
from app.conversation.backends import LLMBackend, build_backend
from app.conversation.config import ContextSettings, ConversationConfig
from app.conversation.facts import merge_facts
from app.conversation.heuristics import cap_summary, heuristic_output, score_message
from app.conversation.manager_llm import ManagerLLM
from app.conversation.models import (
    CompactionReport,
    Fact,
    Message,
    Role,
    TurnMetrics,
)
from app.conversation.pricing import PriceTable
from app.core.logging_config import get_logger

log = get_logger("conversation.manager")
LEADING_USER_PLACEHOLDER = "(Earlier messages are summarized in the system prompt.)"


@dataclass
class ContextWindow:
    """What is sent to the main model this turn."""

    system: str
    messages: list[dict]
    tokens: int
    usage_ratio: float


class ConversationManager:
    def __init__(
        self,
        system_prompt: str,
        settings: ContextSettings,
        counter: TokenCounter,
        manager: ManagerLLM | None = None,
        prices: PriceTable | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.settings = settings
        self.counter = counter
        self.manager = manager
        self.prices = prices or PriceTable({})
        self.messages: list[Message] = []
        self.facts: list[Fact] = []
        self.summary = ""
        self.turn = 0
        self.last_compaction_turn: int | None = None
        self.reports: list[CompactionReport] = []
        self.metrics: list[TurnMetrics] = []
        self._ids = itertools.count(1)
        self._system_prompt_tokens = counter.count(system_prompt)

    # --- every turn: cheap bookkeeping -------------------------------------------------

    def add(self, role: Role, content: str, pinned: bool = False) -> Message:
        if role == "user":
            self.turn += 1
        msg = Message(
            id=f"m{next(self._ids)}",
            role=role,
            content=content,
            turn=self.turn,
            timestamp=time.time(),
            tokens=self.counter.count(content),
            pinned=pinned,
        )
        self.messages.append(msg)
        return msg

    def pin(self, msg_id: str, pinned: bool = True) -> None:
        for msg in self.messages:
            if msg.id == msg_id:
                msg.pinned = pinned
                return
        raise KeyError(msg_id)

    def system_block(self) -> str:
        parts = [self.system_prompt]
        if self.facts or self.summary:
            parts.append("Context kept by ACWM from earlier in this conversation:")
        if self.facts:
            facts = "\n".join(f"- {f.text}" for f in self.facts)
            parts.append(f"<pinned_facts>\n{facts}\n</pinned_facts>")
        if self.summary:
            parts.append(f"<conversation_summary>\n{self.summary}\n</conversation_summary>")
        return "\n\n".join(parts)

    def usage_tokens(self) -> int:
        overhead = self.settings.per_message_overhead_tokens
        if self.facts or self.summary:
            system_tokens = self.counter.count(self.system_block())
        else:
            system_tokens = self._system_prompt_tokens
        return system_tokens + sum(m.tokens + overhead for m in self.messages)

    def usage_ratio(self) -> float:
        return self.usage_tokens() / self.settings.total_tokens

    def should_compact(self) -> bool:
        """LLM compaction trigger: over the threshold and outside the cooldown."""
        if self.usage_ratio() < self.settings.compact_threshold:
            return False
        if self.last_compaction_turn is None:
            return True
        return self.turn - self.last_compaction_turn >= self.settings.cooldown_turns

    def prepare(self) -> tuple[ContextWindow, CompactionReport | None]:
        """Call before each main-model request: compacts when needed, returns the window."""
        report = None
        if self.should_compact():
            report = self.compact(use_llm=True)
        elif self.usage_ratio() > 1.0:
            log.info("Context over budget during cooldown; heuristic compaction (no LLM).")
            report = self.compact(use_llm=False)
        return self.window(), report

    def window(self) -> ContextWindow:
        msgs = [{"role": m.role, "content": m.content} for m in self.messages]
        if msgs and msgs[0]["role"] != "user":
            msgs.insert(0, {"role": "user", "content": LEADING_USER_PLACEHOLDER})
        return ContextWindow(
            system=self.system_block(),
            messages=msgs,
            tokens=self.usage_tokens(),
            usage_ratio=self.usage_ratio(),
        )

    # --- past the threshold: compaction ------------------------------------------------

    def _recent_floor(self) -> int:
        """Messages from this turn onward are the protected recent window."""
        return self.turn - self.settings.keep_recent_turns + 1

    def _compactable(self) -> list[Message]:
        floor = self._recent_floor()
        return [m for m in self.messages if not m.pinned and m.turn < floor]

    def compact(self, use_llm: bool = True) -> CompactionReport:
        s = self.settings
        before = self.usage_tokens()
        report = CompactionReport(
            turn=self.turn, mode="heuristic", tokens_before=before, tokens_after=before
        )
        self.last_compaction_turn = self.turn
        # Messages scored by an earlier compaction were already summarized; they are
        # only eviction candidates now.
        old = [m for m in self._compactable() if m.score is None]
        if not old:
            report.evicted_ids = self._evict_until(s.compact_target)
            report.tokens_after = self.usage_tokens()
            if not report.evicted_ids:
                report.error = "nothing to compact (only recent or pinned messages)"
                log.warning("Compaction skipped at turn %d: %s.", self.turn, report.error)
            self.reports.append(report)
            return report

        batch: list[Message] = []
        batch_tokens = 0
        for msg in old:
            if batch and batch_tokens + msg.tokens > s.max_compaction_input_tokens:
                break
            batch.append(msg)
            batch_tokens += msg.tokens

        output = None
        if use_llm and self.manager is not None:
            call = self.manager.compact(batch, self.summary, self.facts)
            output = call.output
            report.error = call.error
            report.manager_calls = len(call.results)
            report.manager_input_tokens = call.input_tokens
            report.manager_output_tokens = call.output_tokens
            report.manager_latency_ms = call.latency_ms
            report.manager_cost_usd = self.prices.cost(
                self.manager.model, call.input_tokens, call.output_tokens
            )
        if output is not None:
            report.mode = "llm"
        else:
            output = heuristic_output(batch, self.summary, self.counter, s.max_summary_tokens)

        ids = {m.id for m in batch}
        scores = {sc.id: sc.score for sc in output.message_scores if sc.id in ids}
        unknown = {sc.id for sc in output.message_scores} - ids
        if unknown:
            log.warning("Manager scored unknown message ids %s; ignored.", sorted(unknown))
        superseded = set(output.superseded) & ids
        keep: set[str] = set()
        for msg in batch:
            msg.score = scores.get(msg.id) or score_message(msg)
            if msg.id not in superseded and msg.score >= s.verbatim_min_score:
                keep.add(msg.id)

        self.messages = [m for m in self.messages if m.id not in ids or m.id in keep]
        self.summary = cap_summary(output.summary.strip(), self.counter, s.max_summary_tokens)
        self.facts = merge_facts(self.facts, output.pinned_facts, self.turn)
        report.summarized_ids = sorted(ids - keep, key=lambda i: int(i[1:]))
        report.kept_verbatim_ids = sorted(keep, key=lambda i: int(i[1:]))
        report.evicted_ids = self._evict_until(s.compact_target)
        report.tokens_after = self.usage_tokens()
        self.reports.append(report)
        log.info(
            "Compaction turn %d (%s): %d -> %d tokens, %d summarized, %d kept, %d evicted.",
            self.turn,
            report.mode,
            before,
            report.tokens_after,
            len(report.summarized_ids),
            len(report.kept_verbatim_ids),
            len(report.evicted_ids),
        )
        return report

    def eviction_order(self) -> list[Message]:
        """Old, unpinned messages from first to last evicted: lowest score, then oldest."""
        candidates = self._compactable()
        return sorted(
            candidates,
            key=lambda m: (m.score if m.score is not None else score_message(m), m.turn),
        )

    def _evict_until(self, target_ratio: float) -> list[str]:
        evicted: list[str] = []
        for msg in self.eviction_order():
            if self.usage_ratio() <= target_ratio:
                break
            self.messages.remove(msg)
            evicted.append(msg.id)
        if self.usage_ratio() > target_ratio:
            log.warning(
                "Usage %.0f%% still above target %.0f%%: recent turns, pinned messages and "
                "facts alone exceed it.",
                self.usage_ratio() * 100,
                target_ratio * 100,
            )
        return evicted

    # --- instrumentation ---------------------------------------------------------------

    def record_turn(
        self,
        window: ContextWindow,
        report: CompactionReport | None,
        main_model: str,
        main_input_tokens: int | None = None,
        main_output_tokens: int = 0,
    ) -> TurnMetrics:
        """Log one turn. ``main_input_tokens`` defaults to the estimated window size."""
        input_tokens = window.tokens if main_input_tokens is None else main_input_tokens
        m = TurnMetrics(
            turn=self.turn,
            context_tokens=window.tokens,
            usage_ratio=round(window.usage_ratio, 4),
            main_model=main_model,
            main_input_tokens=input_tokens,
            main_output_tokens=main_output_tokens,
            main_cost_usd=self.prices.cost(main_model, input_tokens, main_output_tokens),
        )
        if report is not None:
            m.compaction = report.mode
            m.manager_calls = report.manager_calls
            m.manager_input_tokens = report.manager_input_tokens
            m.manager_output_tokens = report.manager_output_tokens
            m.manager_latency_ms = round(report.manager_latency_ms, 1)
            m.manager_cost_usd = report.manager_cost_usd
        self.metrics.append(m)
        log.info(
            "turn=%d ctx_tokens=%d usage=%.0f%% main_in=%d main_out=%d manager_in=%d "
            "manager_out=%d manager_ms=%.0f cost=$%.5f compaction=%s",
            m.turn,
            m.context_tokens,
            m.usage_ratio * 100,
            m.main_input_tokens,
            m.main_output_tokens,
            m.manager_input_tokens,
            m.manager_output_tokens,
            m.manager_latency_ms,
            m.total_cost_usd,
            m.compaction or "-",
        )
        return m


def build_manager(
    system_prompt: str,
    cfg: ConversationConfig,
    counter: TokenCounter,
    backend: LLMBackend | None = None,
) -> ConversationManager:
    """Wire a ConversationManager from config; ``backend`` overrides the configured one."""
    backend = backend if backend is not None else build_backend("manager", cfg)
    manager_llm = (
        ManagerLLM(backend, json_retries=cfg.manager.json_retries) if backend is not None else None
    )
    return ConversationManager(
        system_prompt, cfg.context, counter, manager_llm, PriceTable(cfg.pricing)
    )
