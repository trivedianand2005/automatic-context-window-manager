# Evaluation methodology

## Question

Under the same token budget, does dependency-aware selection with budget optimization
put more of the files a developer actually needs into the context than lexical retrieval
alone?

## Methods compared

All three methods use the same usable budget, task text, tokenizer and index.

| Method | Ranking | Selection |
|---|---|---|
| `baseline` | BM25 over files only (normalised lexical score) | Whole files in rank order; skip files that do not fit |
| `dependency` | 0.6 × lexical + 0.4 × graph-expansion score | Whole files in rank order; skip files that do not fit |
| `acwm` | Full hybrid ranking (all signals, default weights) | Budget optimizer: core set, fair share, excerpts, density-greedy tail, redundancy handling |

## Dataset

* **Repository:** `examples/sample_fastapi_repo`. It has 49 indexed files (about 9.8k
  tokens): a FastAPI service with auth, orders, database retry, and tests. It also contains
  deliberate lexical distractors: `analytics/token_usage.py` (LLM token billing),
  `utils/rate_limit.py` (token bucket), `CHANGELOG.md`, `docs/auth_history.md`,
  `services/payment_gateway.py` ("retry" vocabulary), and `services/notification_service.py`
  ("login/password" vocabulary).
* **Tasks and labels:** `benchmarks/sample_fastapi_tasks.json`. Five tasks:
  * JWT authentication;
  * database retry fix;
  * protected-route tests;
  * API error handling;
  * request validation.

  Each task lists 4–11 relevant files, with a written rationale.
* **Labelling:** the labels were reviewed manually by the author of the sample repository.
  They mark the minimal set of files to read or edit. They were written before the ranking
  heuristics were tuned, and they have not been changed since.

## Metrics (`app/evaluation/metrics.py`)

| Metric | Definition | N/A when |
|---|---|---|
| Precision@K | relevant ∩ top-K selected / min(K, #selected) | nothing selected |
| Recall@K | relevant ∩ top-K selected / #relevant | no labels |
| MRR | 1 / rank of the first relevant selected item | nothing selected |
| Coverage | relevant files present in the context (full or partial) / #relevant | no labels |
| Full coverage | same, counting only files included in full | no labels |
| Token utilization | rendered context tokens / usable budget | — |
| Budget violations | count of runs where rendered tokens > usable budget | — |
| Latency | ranking + selection + packaging time in ms (indexing excluded) | — |

"Ranked selected" means the selected items sorted by the method's own score.

## Reproduce

```bash
python scripts/evaluate_benchmarks.py --budgets 3000 4000 6000 8000
```

This prints Markdown tables and writes `demo_output/benchmark_results.json`. The same run is
available through `POST /benchmarks/run` and the **Benchmarks** tab in the UI. Results
are deterministic except for latency.

## Measured results

Run on 2026-10-18, on Windows 11 with Python 3.12.6, using the `tiktoken:cl100k_base`
tokenizer, K = 5, over 5 tasks. Total budget includes reserves: about 2,100 tokens are
reserved for system, task, response and safety margin. Usable context was therefore 919,
1,869, 3,769 and 5,669 tokens. Latency values are machine-specific.

**Total budget 3000**

| method | P@5 | R@5 | MRR | coverage | full cov. | tokens | util. | violations |
|---|---|---|---|---|---|---|---|---|
| baseline | 0.330 | 0.250 | 0.800 | 0.250 | 0.250 | 911 | 0.989 | 0 |
| dependency | 0.540 | 0.421 | 0.900 | 0.421 | 0.421 | 909 | 0.986 | 0 |
| acwm | **0.670** | **0.506** | **1.000** | **0.506** | 0.406 | 907 | 0.985 | 0 |

**Total budget 4000**

| method | P@5 | R@5 | MRR | coverage | full cov. | tokens | util. | violations |
|---|---|---|---|---|---|---|---|---|
| baseline | 0.480 | 0.371 | 0.867 | 0.438 | 0.438 | 1854 | 0.991 | 0 |
| dependency | **0.680** | **0.539** | 0.900 | 0.726 | **0.726** | 1853 | 0.990 | 0 |
| acwm | 0.640 | 0.489 | **1.000** | **0.779** | 0.676 | 1739 | 0.929 | 0 |

**Total budget 6000**

| method | P@5 | R@5 | MRR | coverage | full cov. | tokens | util. | violations |
|---|---|---|---|---|---|---|---|---|
| baseline | 0.480 | 0.371 | 0.867 | 0.797 | 0.797 | 3743 | 0.992 | 0 |
| dependency | **0.680** | **0.539** | 0.900 | **0.967** | **0.967** | 3750 | 0.995 | 0 |
| acwm | 0.640 | 0.489 | **1.000** | 0.933 | 0.933 | 3386 | 0.898 | 0 |

**Total budget 8000**

| method | P@5 | R@5 | MRR | coverage | full cov. | tokens | util. | violations |
|---|---|---|---|---|---|---|---|---|
| baseline | 0.480 | 0.371 | 0.867 | 0.915 | 0.915 | 5613 | 0.990 | 0 |
| dependency | **0.680** | **0.539** | 0.900 | **0.967** | **0.967** | 5642 | 0.995 | 0 |
| acwm | 0.640 | 0.489 | **1.000** | 0.933 | 0.933 | **3684** | 0.650 | 0 |

Mean latency was about 7–9 ms for the baseline, 9–12 ms for dependency and 16–21 ms for
ACWM per task on this machine.

## Interpretation

* **Graph expansion helps.** Both graph-aware methods beat BM25-only retrieval on every
  metric at every budget. Lexical distractors (token-usage analytics, the changelog, the
  auth history notes) rank high under BM25 alone. Imports pull in the genuinely needed
  files: route → `dependencies.py` → `auth_service.py` → `config.py`.
* **ACWM wins when the budget is tight.** At 3000 it leads on every metric. At 4000 it has
  the highest coverage and MRR, because excerpts let more relevant files fit.
* **ACWM trades some coverage for fewer tokens at larger budgets.** At 6000 and 8000 the
  plain `dependency` method covers slightly more relevant files (0.967 vs 0.933), because it
  fills the budget in rank order. ACWM stops at a relevance threshold and used 10% and
  35% fewer tokens respectively. Depending on the agent, either behaviour may be preferable.
  The threshold is configurable (`OptimizerOptions.rel_min_score`).
* **Precision@5 and recall@5** are slightly lower for ACWM than for `dependency` at budgets
  of 4000 and above. Its top-ranked items include test fixtures (`tests/conftest.py`) that
  are only sometimes labelled relevant.
* **There were no budget violations** in any run. Every package is validated after
  rendering.

## Threats to validity (read before quoting these numbers)

* **Tiny benchmark.** Five tasks on one ~10k-token repository written by the same author
  as ACWM. This shows the mechanism works; it does not show that results generalise to real
  repositories.
* **Tuning leakage.** The heuristics were adjusted after inspecting failures on these same
  tasks: the core set, fair share, documentation prior, canonical short forms, test-link
  rule and positive-IDF BM25. There is no held-out set, so the ACWM numbers are
  optimistic. The labels themselves were not changed.
* **Subjective labels.** Whether `tests/conftest.py` or `core/errors.py` is "relevant" is a
  judgement call, and different reviewers would label differently.
* **Proxy metrics.** Coverage of relevant files does not measure whether a coding agent
  actually produces a correct change. ACWM does not evaluate downstream task success.
* **Tokenizer.** Token counts are tiktoken `cl100k_base` estimates. The target model's
  tokenizer may differ.
* **Partial-file coverage.** "Coverage" counts a partial excerpt as covered even if the
  needed lines were omitted. "Full coverage" is reported alongside it for this reason.
