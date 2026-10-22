import json
import re

import httpx
import pytest

from app.context.token_counter import get_token_counter
from app.conversation.backends import (
    AnthropicBackend,
    MockBackend,
    OllamaBackend,
    build_backend,
)
from app.conversation.config import (
    ContextSettings,
    ConversationConfig,
    ModelSettings,
    load_conversation_config,
)
from app.conversation.facts import fact_key, merge_facts
from app.conversation.heuristics import mock_manager_responder
from app.conversation.manager import ConversationManager
from app.conversation.manager_llm import ManagerLLM
from app.conversation.models import Fact
from app.conversation.pricing import PriceTable
from app.conversation.structured import InvalidManagerOutput, parse_manager_output
from app.core.exceptions import ProviderError

COUNTER = get_token_counter("cl100k_base")
FILLER = "We talked about refactoring the helper module and renaming a few variables today."

# --- config + backends ---------------------------------------------------------------


def test_config_yaml_loads_and_validates(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "manager:\n  backend: ollama\ncontext:\n  total_tokens: 1000\n  compact_threshold: 0.8\n",
        encoding="utf-8",
    )
    cfg = load_conversation_config(path)
    assert cfg.manager.backend == "ollama"
    assert cfg.context.total_tokens == 1000
    assert cfg.context.compact_target == 0.5
    assert load_conversation_config(tmp_path / "missing.yaml").manager.model == "claude-haiku-5-5"


def test_project_config_yaml_is_valid():
    cfg = load_conversation_config()
    assert cfg.manager.model != cfg.main_model.model
    assert cfg.context.compact_target < cfg.context.compact_threshold


def test_target_must_be_below_threshold():
    with pytest.raises(ValueError):
        ContextSettings(compact_threshold=0.5, compact_target=0.6)


def test_anthropic_backend_without_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    backend = AnthropicBackend(ModelSettings())
    assert not backend.available
    with pytest.raises(ProviderError):
        backend.complete("s", [{"role": "user", "content": "hi"}])
    assert build_backend("manager", ConversationConfig()) is None


def test_build_backend_selects_ollama_and_none():
    cfg = ConversationConfig(manager=ModelSettings(backend="ollama"))
    backend = build_backend("manager", cfg)
    assert isinstance(backend, OllamaBackend) and backend.model == cfg.ollama.manager_model
    assert (
        build_backend("manager", ConversationConfig(manager=ModelSettings(backend="none"))) is None
    )


def test_ollama_backend_parses_usage_and_maps_errors(monkeypatch):
    def ok(url, json, timeout):
        assert json["format"] == {"type": "object"} and json["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json={"message": {"content": "{}"}, "prompt_eval_count": 12, "eval_count": 3},
            request=httpx.Request("POST", url),
        )

    backend = OllamaBackend(ModelSettings(), "http://ollama:11434/", "qwen2.5:7b", 0.1)
    monkeypatch.setattr(httpx, "post", ok)
    result = backend.complete(
        "s", [{"role": "user", "content": "x"}], json_schema={"type": "object"}
    )
    assert (result.text, result.input_tokens, result.output_tokens) == ("{}", 12, 3)

    def timeout(url, json, timeout):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "post", timeout)
    with pytest.raises(ProviderError, match="timed out"):
        backend.complete("s", [])


def test_mock_backend_scripts_and_raises():
    backend = MockBackend(["one", ProviderError("boom")])
    assert backend.complete("s", [{"role": "user", "content": "abcd"}]).text == "one"
    with pytest.raises(ProviderError, match="boom"):
        backend.complete("s", [])
    with pytest.raises(ProviderError):
        backend.complete("s", [])


def test_price_table():
    table = PriceTable(ConversationConfig().pricing)
    assert table.cost("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert table.cost("unknown-model", 100, 100) == 0.0


# --- hybrid manager ------------------------------------------------------------------


def ctx(**overrides) -> ContextSettings:
    base = dict(
        total_tokens=400,
        compact_threshold=0.75,
        compact_target=0.5,
        keep_recent_turns=2,
        cooldown_turns=3,
        max_summary_tokens=60,
    )
    return ContextSettings(**{**base, **overrides})


def ids_in(messages: list[dict]) -> list[str]:
    return re.findall(r'<message id="([^"]+)"', messages[-1]["content"])


def valid_reply(score: int = 2, facts=("deadline: November 14",), superseded=()):
    def respond(_system, messages):
        return json.dumps(
            {
                "summary": "Earlier: refactoring chat.",
                "pinned_facts": list(facts),
                "message_scores": [
                    {"id": i, "score": score, "reason": "test"} for i in ids_in(messages)
                ],
                "superseded": list(superseded),
            }
        )

    return respond


def raising(exc: Exception):
    def respond(_system, _messages):
        raise exc

    return respond


def make(backend=None, **overrides) -> ConversationManager:
    llm = ManagerLLM(backend, json_retries=1) if backend is not None else None
    return ConversationManager("You are a helpful assistant.", ctx(**overrides), COUNTER, llm)


def chat(mgr: ConversationManager, turns: int, text: str = FILLER):
    reports = []
    for _ in range(turns):
        mgr.add("user", text)
        _, report = mgr.prepare()
        reports.append(report)
        mgr.add("assistant", text)
    return reports


def test_no_llm_call_below_threshold():
    backend = MockBackend(valid_reply())
    mgr = make(backend)
    chat(mgr, 2)
    assert mgr.usage_ratio() < 0.75
    assert backend.calls == []
    assert all(m.tokens > 0 and m.turn >= 1 for m in mgr.messages)


def test_threshold_triggers_compaction_to_target_and_keeps_recent():
    backend = MockBackend(valid_reply())
    mgr = make(backend)
    reports = chat(mgr, 12)
    fired = [r for r in reports if r is not None]
    assert fired and fired[0].mode == "llm"
    assert fired[0].tokens_before >= 0.75 * 400
    assert fired[0].tokens_after <= 0.5 * 400
    floor = mgr.turn - 2 + 1
    assert {m.turn for m in mgr.messages if m.turn >= floor} == {mgr.turn - 1, mgr.turn}
    window = mgr.window()
    assert "<pinned_facts>" in window.system and "deadline: November 14" in window.system
    assert window.system.startswith("You are a helpful assistant.")
    assert window.messages[0]["role"] == "user"


def test_cooldown_prevents_back_to_back_compaction():
    backend = MockBackend(valid_reply())
    # A large recent window keeps usage above the threshold right after compaction.
    mgr = make(backend, keep_recent_turns=3, total_tokens=300)
    reports = chat(mgr, 14)
    llm_turns = [r.turn for r in reports if r is not None and r.mode == "llm"]
    assert len(llm_turns) >= 2
    assert all(b - a >= 3 for a, b in zip(llm_turns, llm_turns[1:], strict=False))


def test_overflow_during_cooldown_uses_heuristics_without_llm():
    backend = MockBackend(valid_reply())
    mgr = make(backend, keep_recent_turns=1, cooldown_turns=50, total_tokens=300)
    reports = chat(mgr, 14)
    assert len(backend.calls) == 1
    assert any(r is not None and r.mode == "heuristic" for r in reports)
    assert mgr.usage_ratio() <= 1.0


def test_parse_manager_output_validates_schema():
    good = parse_manager_output(
        '```json\n{"summary": "s", "pinned_facts": [], "message_scores": '
        '[{"id": "m1", "score": 5, "reason": "r"}], "superseded": []}\n```'
    )
    assert good.message_scores[0].score == 5
    with pytest.raises(InvalidManagerOutput, match="invalid JSON"):
        parse_manager_output('{"summary": "s", }')
    with pytest.raises(InvalidManagerOutput, match="no JSON"):
        parse_manager_output("I cannot do that")
    with pytest.raises(InvalidManagerOutput, match="schema mismatch"):
        parse_manager_output(
            '{"summary": "s", "pinned_facts": [], '
            '"message_scores": [{"id": "m1", "score": 9, "reason": "r"}]}'
        )


def test_invalid_json_retries_once_with_repair_prompt():
    good = valid_reply()
    backend = MockBackend(lambda s, m: "not json" if len(backend.calls) == 1 else good(s, m))
    mgr = make(backend)
    reports = chat(mgr, 12)
    first = next(r for r in reports if r is not None)
    assert first.mode == "llm" and first.manager_calls == 2
    assert "could not be used" in backend.calls[1][1][0]["content"]


def test_invalid_json_twice_falls_back_to_heuristics():
    backend = MockBackend(lambda s, m: '{"summary": 1}')
    mgr = make(backend)
    mgr.add("user", "Remember: the deadline is November 14 for the launch.")
    mgr.add("assistant", "Noted.")
    reports = chat(mgr, 12)
    first = next(r for r in reports if r is not None)
    assert first.mode == "heuristic" and first.manager_calls == 2
    assert "invalid manager output" in first.error
    assert any("November 14" in f.text for f in mgr.facts)


@pytest.mark.parametrize("failure", [ProviderError("LLM request timed out."), RuntimeError("x")])
def test_manager_failure_never_crashes(failure):
    mgr = make(MockBackend(raising(failure)))
    reports = chat(mgr, 12)
    first = next(r for r in reports if r is not None)
    assert first.mode == "heuristic" and "manager call failed" in first.error
    assert mgr.usage_ratio() <= 0.75


def test_no_manager_configured_uses_heuristics():
    mgr = make(None)
    reports = chat(mgr, 12)
    assert any(r is not None and r.mode == "heuristic" for r in reports)


def test_fact_merge_newer_wins_and_dedupes():
    facts = merge_facts([], ["database: PostgreSQL 16", "api port: 8081"], turn=3)
    facts = merge_facts(
        facts,
        ["Database: switched to SQLite", "API port: 8081.", "deadline: November 14"],
        turn=40,
    )
    texts = [f.text for f in facts]
    assert texts == ["Database: switched to SQLite", "API port: 8081.", "deadline: November 14"]
    assert facts[0].turn == 40
    assert fact_key("database: x") == "database" and fact_key("no topic here") is None
    # Same batch: the later item wins.
    assert [f.text for f in merge_facts([], ["owner: Ana", "owner: Ravi"], 1)] == ["owner: Ravi"]
    # Unrelated facts without a key are both kept.
    assert len(merge_facts([Fact(text="uses pytest", turn=1)], ["prefers tabs"], 2)) == 2


def test_eviction_order_lowest_score_then_oldest_and_protects_pinned_recent():
    mgr = make(None, keep_recent_turns=1)
    a = mgr.add("user", "alpha " * 20)
    b = mgr.add("user", "bravo " * 20)
    c = mgr.add("user", "charlie " * 20)
    d = mgr.add("user", "delta " * 20)
    pinned = mgr.add("user", "pinned " * 20, pinned=True)
    recent = mgr.add("user", "recent " * 20)
    a.score, b.score, c.score, d.score = 3, 1, 3, 5
    assert [m.id for m in mgr.eviction_order()] == [b.id, a.id, c.id, d.id]
    mgr._evict_until(0.0)
    assert {m.id for m in mgr.messages} == {pinned.id, recent.id}


def test_superseded_messages_are_dropped_even_if_high_scoring():
    first_ids: list[str] = []

    def respond(system, messages):
        ids = ids_in(messages)
        first_ids.extend(ids)
        return valid_reply(score=5, superseded=ids[:1])(system, messages)

    mgr = make(MockBackend(respond), compact_target=0.7)
    for _ in range(30):
        if chat(mgr, 1)[0] is not None:
            break
    remaining = {m.id for m in mgr.messages}
    assert first_ids and first_ids[0] not in remaining
    assert any(i in remaining for i in first_ids[1:])


def test_mock_responder_returns_schema_valid_json():
    mgr = make(MockBackend(mock_manager_responder(COUNTER, 60)))
    mgr.add("user", "My name is Priya and the deadline is November 14.")
    mgr.add("assistant", "Got it.")
    reports = chat(mgr, 12)
    assert next(r for r in reports if r is not None).mode == "llm"
    assert any("deadline" in f.text for f in mgr.facts)


def test_record_turn_metrics_include_manager_usage_and_cost():
    mgr = make(MockBackend(valid_reply(), model="claude-haiku-5-5"))
    mgr.prices = PriceTable(ConversationConfig().pricing)
    for _ in range(12):
        mgr.add("user", FILLER)
        window, report = mgr.prepare()
        m = mgr.record_turn(window, report, "claude-opus-5-5", main_output_tokens=20)
        mgr.add("assistant", FILLER)
        if report is not None:
            break
    assert m.compaction == "llm" and m.manager_input_tokens > 0 and m.manager_cost_usd > 0
    assert m.main_input_tokens == window.tokens and m.main_cost_usd > 0


# --- benchmark -----------------------------------------------------------------------


def test_dry_run_benchmark_runs_all_strategies_without_keys():
    from app.evaluation.conversation_benchmark import run_benchmark
    from app.evaluation.conversation_dataset import build_dataset

    dataset = build_dataset()
    assert 60 <= len(dataset) <= 100 and dataset == build_dataset()
    results = run_benchmark(ConversationConfig(), dataset, COUNTER, 4000, dry_run=True)
    summary = {s["strategy"]: s for s in results["summary"]}
    assert summary["full"]["overflow_turn"] is not None
    assert summary["truncation"]["turns_completed"] == len(dataset)
    acwm = summary["acwm"]
    assert acwm["compactions"] >= 1 and acwm["manager_calls"] >= 1
    assert acwm["recall_accuracy"] > summary["truncation"]["recall_accuracy"]
    assert acwm["main_input_tokens"] < summary["truncation"]["main_input_tokens"]
    assert max(t["context_tokens"] for t in results["per_turn"]["acwm"]) <= 4000
