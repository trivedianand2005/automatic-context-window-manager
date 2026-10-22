# Changelog

## Unreleased: conversation manager in the web app

### Added

- **Conversation page** in the web app: runs the conversation benchmark on the server and
  shows the models in use, context size per turn (with compactions and the no-management
  overflow marked), cost and recall charts, a summary table, compaction events and
  per-question results.
- **API**: `GET /conversation/status` (public) and `POST /conversation/benchmark`
  (dry-run by default and cached; live runs need `ACWM_CONVERSATION_LIVE=true`, one at a
  time, 600 s timeout).
- `conversation_manager` row in `/health` providers (shown on Overview).
- Tests: API tests for the new endpoints and auth, a frontend unit test and a Playwright
  test for the Conversation page.

### Changed

- The optional repository `llm` provider row is no longer shown in `/health` (and on the
  Overview page) until `ACWM_LLM_PROVIDER` is configured, so the live site no longer shows
  "unconfigured (no LLM provider configured)".
- README, `docs/api.md`, `.env.example` and `render.yaml` document the new page,
  endpoints and `ACWM_CONVERSATION_LIVE`.

## Unreleased: hybrid conversation manager

### Added

- **Conversation manager** (`app/conversation/`): keeps a long chat under a token budget.
  - Every turn, without an LLM: token counts and per-message metadata (role, turn,
    timestamp, tokens, pinned flag, score).
  - Past `compact_threshold` (75%), a small manager model compacts older messages into a
    pinned-facts block (never evicted), a running summary and any high-scoring messages.
    It then evicts the lowest-scored messages until usage is at or below `compact_target`
    (50%). The system prompt and the last N turns (4) always stay verbatim.
  - Cooldown and threshold/target hysteresis. Heuristic-only compaction if the context
    would overflow during a cooldown.
- **Pluggable backends** (`backends.py`): Anthropic (manager `claude-haiku-5-5`, main
  `claude-opus-5-5`, with server-side refusal fallback on the main model), Ollama (local,
  e.g. `qwen2.5:7b`), and a mock for tests and dry runs. The manager model is used only for
  context management. The main model only answers.
- **Structured output** (`models.py`, `structured.py`, `prompts.py`): `ManagerOutput`
  pydantic schema, also sent as a JSON-schema structured output. Every reply is validated,
  with one error-correction retry, then a fall back to heuristics. Prompts are in their own
  file.
- **Fact merging** (`facts.py`): near-duplicates are deduped, and for the same `topic:` the
  newer fact wins.
- **Graceful failure**: timeouts, API errors, refusals and invalid JSON log a warning and
  fall back to heuristics (`heuristics.py`). A manager failure never breaks a turn.
- **Metrics**: per-turn `TurnMetrics` and log line covering main-model tokens, manager
  tokens, manager latency, estimated cost (prices in `config.yaml`) and whether compaction
  fired.
- **Benchmark** (`scripts/conversation_benchmark.py`, `make conv-bench`): one 80-turn
  synthetic conversation with planted facts, run through no management, naive truncation
  and ACWM. Writes JSON/CSV results and three PNG charts. `--dry-run` needs no API keys.
  Optional LLM judge with `--judge llm`.
- **`config.yaml`**: one file for every model name, backend, threshold and price
  (`ACWM_CONFIG` selects another file).
- 24 unit tests in `tests/unit/test_conversation.py`, all using a mocked manager LLM.

### Changed

- `requirements.txt` / `pyproject.toml`: added `pyyaml`. `requirements-optional.txt`:
  added `matplotlib` for the benchmark charts.
- README: new "Conversation manager (hybrid LLM)" section. `.env.example`: documents
  `ACWM_CONFIG`. Makefile: `conv-bench` target.

The existing repository-context pipeline is unchanged.
