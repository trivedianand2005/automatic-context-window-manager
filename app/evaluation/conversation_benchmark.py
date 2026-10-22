"""Run one long conversation through three context strategies and measure each.

    full        no management: send everything until the context overflows the budget
    truncation  naive: drop the oldest messages until the context fits the budget
    acwm        hybrid manager: heuristics every turn, manager LLM past the threshold

Filler turns use scripted assistant replies so every strategy sees the same text; the
main model is only called on recall-question turns. Main-model tokens and cost for
filler turns are estimates (tiktoken count of the window x configured price). Manager
tokens come from the backend's reported usage (estimated in mock mode).

In dry-run mode the main model is a mock that returns its whole context window, so
"accuracy" measures whether the planted fact survived in what the model was sent
(fact retention), not answer quality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.context.token_counter import TokenCounter
from app.conversation.backends import LLMBackend, MockBackend, build_backend
from app.conversation.config import ConversationConfig
from app.conversation.heuristics import mock_manager_responder
from app.conversation.manager import ContextWindow, ConversationManager, build_manager
from app.conversation.models import CompactionReport, TurnMetrics
from app.conversation.pricing import PriceTable
from app.conversation.prompts import JUDGE_PROMPT, JUDGE_SYSTEM
from app.core.logging_config import get_logger
from app.evaluation.conversation_dataset import SYSTEM_PROMPT, RecallQuestion, Turn

log = get_logger("evaluation.conversation")
STRATEGIES = ("full", "truncation", "acwm")
DRY_RUN_REPLY = "Here is what I know from our conversation so far."


class FullContext(ConversationManager):
    """No management at all."""

    def prepare(self) -> tuple[ContextWindow, CompactionReport | None]:
        return self.window(), None


class NaiveTruncation(ConversationManager):
    """Drop the oldest messages (never the newest one) until the window fits the budget."""

    def prepare(self) -> tuple[ContextWindow, CompactionReport | None]:
        while self.usage_ratio() > 1.0 and len(self.messages) > 1:
            self.messages.pop(0)
        return self.window(), None


@dataclass
class Answer:
    question_id: str
    turn: int
    fact_turn: int
    question: str
    expected_keywords: list[str]
    answer: str
    correct: bool


@dataclass
class StrategyResult:
    name: str
    turns: list[TurnMetrics] = field(default_factory=list)
    answers: list[Answer] = field(default_factory=list)
    overflow_turn: int | None = None
    compactions: int = 0
    manager_failures: int = 0

    def summary(self, total_questions: int) -> dict:
        correct = sum(a.correct for a in self.answers)
        return {
            "strategy": self.name,
            "turns_completed": len(self.turns),
            "overflow_turn": self.overflow_turn,
            "main_input_tokens": sum(t.main_input_tokens for t in self.turns),
            "main_output_tokens": sum(t.main_output_tokens for t in self.turns),
            "manager_input_tokens": sum(t.manager_input_tokens for t in self.turns),
            "manager_output_tokens": sum(t.manager_output_tokens for t in self.turns),
            "total_tokens": sum(
                t.main_input_tokens
                + t.main_output_tokens
                + t.manager_input_tokens
                + t.manager_output_tokens
                for t in self.turns
            ),
            "main_cost_usd": round(sum(t.main_cost_usd for t in self.turns), 6),
            "manager_cost_usd": round(sum(t.manager_cost_usd for t in self.turns), 6),
            "total_cost_usd": round(sum(t.total_cost_usd for t in self.turns), 6),
            "manager_calls": sum(t.manager_calls for t in self.turns),
            "manager_latency_ms": round(sum(t.manager_latency_ms for t in self.turns), 1),
            "compactions": self.compactions,
            "manager_failures": self.manager_failures,
            "recall_correct": correct,
            "recall_total": total_questions,
            "recall_accuracy": round(correct / total_questions, 4) if total_questions else 0.0,
        }


def keyword_correct(answer: str, q: RecallQuestion) -> bool:
    low = answer.lower()
    return all(k.lower() in low for k in q.expected_keywords)


class Judge:
    """Keyword grading, or LLM-as-judge with keyword grading as the fallback."""

    def __init__(self, backend: LLMBackend | None = None) -> None:
        self.backend = backend

    def __call__(self, question: str, answer: str, q: RecallQuestion) -> bool:
        if self.backend is None:
            return keyword_correct(answer, q)
        prompt = JUDGE_PROMPT.format(
            question=question, expected=", ".join(q.expected_keywords), answer=answer[:4000]
        )
        schema = {
            "type": "object",
            "properties": {"correct": {"type": "boolean"}},
            "required": ["correct"],
            "additionalProperties": False,
        }
        try:
            text = self.backend.complete(
                JUDGE_SYSTEM, [{"role": "user", "content": prompt}], 64, schema
            ).text
            return bool(json.loads(text[text.find("{") : text.rfind("}") + 1])["correct"])
        except Exception as exc:  # noqa: BLE001 - grading must not abort the benchmark
            log.warning("LLM judge failed (%s); using keyword grading.", exc)
            return keyword_correct(answer, q)


def context_echo(system: str, messages: list[dict]) -> str:
    """Dry-run main model: 'answers' with everything it was sent."""
    return "\n".join([system, *(str(m["content"]) for m in messages)])


def make_strategy(
    name: str,
    cfg: ConversationConfig,
    counter: TokenCounter,
    budget: int,
    manager_backend: LLMBackend | None,
) -> ConversationManager:
    settings = cfg.context.model_copy(update={"total_tokens": budget})
    cfg = cfg.model_copy(update={"context": settings})
    prices = PriceTable(cfg.pricing)
    if name == "full":
        return FullContext(SYSTEM_PROMPT, settings, counter, None, prices)
    if name == "truncation":
        return NaiveTruncation(SYSTEM_PROMPT, settings, counter, None, prices)
    return build_manager(SYSTEM_PROMPT, cfg, counter, backend=manager_backend)


def run_strategy(
    name: str,
    dataset: list[Turn],
    cfg: ConversationConfig,
    counter: TokenCounter,
    budget: int,
    main: LLMBackend,
    manager_backend: LLMBackend | None,
    judge: Judge,
    dry_run: bool,
) -> StrategyResult:
    strategy = make_strategy(name, cfg, counter, budget, manager_backend)
    result = StrategyResult(name)
    main_model = cfg.main_model.model
    for turn in dataset:
        strategy.add("user", turn.user)
        window, report = strategy.prepare()
        if report is not None:
            result.compactions += 1
            result.manager_failures += int(report.error is not None and report.mode != "llm")
        if window.tokens > budget:
            if name == "full":
                result.overflow_turn = turn.turn
                log.info("%s: context overflowed the budget at turn %d.", name, turn.turn)
                break
            log.warning("%s: window %d exceeds budget %d.", name, window.tokens, budget)

        if turn.question is not None:
            try:
                res = main.complete(window.system, window.messages)
                answer, in_tok, out_tok = res.text, res.input_tokens, res.output_tokens
            except Exception as exc:  # noqa: BLE001 - a failed answer is a wrong answer
                log.warning("%s: main model failed at turn %d (%s).", name, turn.turn, exc)
                answer, in_tok, out_tok = "", window.tokens, 0
            if dry_run:
                # The echo is the "answer" for grading; store a short reply instead.
                in_tok, reply = window.tokens, DRY_RUN_REPLY
                out_tok = counter.count(reply)
            else:
                reply = answer or "(no answer)"
            q = turn.question
            result.answers.append(
                Answer(
                    question_id=q.id,
                    turn=turn.turn,
                    fact_turn=q.fact_turn,
                    question=turn.user,
                    expected_keywords=q.expected_keywords,
                    answer=answer if not dry_run else "(context echo)",
                    correct=judge(turn.user, answer, q),
                )
            )
            result.turns.append(strategy.record_turn(window, report, main_model, in_tok, out_tok))
        else:
            reply = turn.assistant or ""
            result.turns.append(
                strategy.record_turn(window, report, main_model, None, counter.count(reply))
            )
        strategy.add("assistant", reply)
    return result


def run_benchmark(
    cfg: ConversationConfig,
    dataset: list[Turn],
    counter: TokenCounter,
    budget: int,
    dry_run: bool,
    judge_mode: str = "keyword",
    strategies: tuple[str, ...] = STRATEGIES,
) -> dict:
    if dry_run:
        main: LLMBackend = MockBackend(context_echo, model=cfg.main_model.model)
        manager_backend: LLMBackend | None = MockBackend(
            mock_manager_responder(counter, cfg.context.max_summary_tokens),
            model=cfg.manager.model,
        )
        judge = Judge()
    else:
        built = build_backend("main_model", cfg)
        if built is None:
            raise RuntimeError(
                "Main model backend unavailable (set ANTHROPIC_API_KEY or change "
                "main_model.backend in config.yaml), or run with --dry-run."
            )
        main = built
        manager_backend = build_backend("manager", cfg)
        if manager_backend is None:
            log.warning("Manager backend unavailable; ACWM will use heuristics only.")
        judge = Judge(build_backend("manager", cfg) if judge_mode == "llm" else None)

    total_q = sum(t.question is not None for t in dataset)
    results = [
        run_strategy(name, dataset, cfg, counter, budget, main, manager_backend, judge, dry_run)
        for name in strategies
    ]
    return {
        "mode": "dry-run (mock models; accuracy = fact retention in context)"
        if dry_run
        else "live",
        "budget_tokens": budget,
        "main_model": cfg.main_model.model,
        "manager_model": cfg.manager.model,
        "judge": "keyword" if dry_run else judge_mode,
        "turns": len(dataset),
        "recall_questions": total_q,
        "summary": [r.summary(total_q) for r in results],
        "per_turn": {r.name: [t.model_dump() for t in r.turns] for r in results},
        "answers": {r.name: [a.__dict__ for a in r.answers] for r in results},
    }
