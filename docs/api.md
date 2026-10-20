# ACWM REST API

Start the server:

```bash
uvicorn app.api.main:app --reload --port 8000
```

Interactive OpenAPI docs are served at <http://127.0.0.1:8000/docs>, and the raw schema
at `/openapi.json`.

All request and response bodies are JSON validated by Pydantic. Relative repository
paths are resolved against the server's working directory.

## Errors

Every error uses this shape:

```json
{"error": {"code": "path_not_allowed", "message": "Repository path is outside the allowed roots. ...", "details": {"allowed_roots": ["..."]}}}
```

| Status | `code` | Cause |
|---|---|---|
| 400 | `invalid_repository` | Path does not exist or is not a directory |
| 403 | `path_not_allowed` | Path outside allowed roots, path traversal in `required_paths`, or null bytes |
| 404 | `repository_not_found` | Unknown `repository_id` (index it first; indexes live in memory) |
| 413 | `request_too_large` | Body exceeds `api_max_request_bytes` (default 1 MB) |
| 422 | `validation_error` | Request validation failed (`details` lists the fields) |
| 422 | `budget_exceeded` | Budget too small after reservations, or required files exceed it |
| 504 | `processing_timeout` | Processing exceeded `api_timeout_seconds` (default 60 s) |
| 500 | `internal_error` | Unexpected error (details are logged server-side, not returned) |

## Endpoints

## Accounts and authentication

* **Log in.** `POST /auth/signup` with `{"email", "password", "display_name"?}` or
  `POST /auth/login` with `{"email", "password"}` returns
  `{"token", "token_type": "bearer", "expires_in_minutes", "user"}`.
* **Use the token.** Send `Authorization: Bearer <token>` on later requests. In `/docs`, use
  the **Authorize** button.
* **Login required in production.** With `ACWM_REQUIRE_AUTH=true` (set on Render), every
  repository, context, compare, export, runs and benchmark-run endpoint returns
  `401 not_authenticated` without a valid token. `/health`, `/config`, `/benchmarks` and
  `/auth/*` stay public.
* **Isolation.** A logged-in user's requests always use that user's own workspace (indexes
  and runs), whatever `X-ACWM-Session` says.
* **GitHub.** `GET /auth/github/login` redirects to GitHub (scope `read:user`, `state`, PKCE
  S256) and sets a short-lived HttpOnly cookie. GitHub calls back to
  `GET /auth/github/callback`, which redirects to `ACWM_FRONTEND_URL` with
  `#auth_token=<jwt>` or `#auth_error=<message>` in the URL fragment. The web app reads the
  fragment and removes it from the address bar.

| Endpoint | Auth | Result |
|---|---|---|
| `GET /auth/providers` | — | `{email_password, github, require_auth, database}` |
| `POST /auth/signup` | — | 201 token; 409 `account_exists`; 422 `invalid_input` (email format, password 8–128 chars) |
| `POST /auth/login` | — | 200 token; 401 `not_authenticated`; 429 `rate_limited` after 10 failures in 5 minutes |
| `GET /auth/me` | Bearer | The current user |
| `GET /packages` | Bearer | This user's saved packages (newest first, summaries only) |
| `POST /packages` | Bearer | `{"title"?, "package": ContextPackage}` → 201 summary; 409 `quota_exceeded` above 50 |
| `GET /packages/{id}` | Bearer | Summary + full package; 404 if it does not exist or belongs to someone else |
| `DELETE /packages/{id}` | Bearer | 204; same 404 rule |

## Sessions and CORS

* **Sessions.** Clients may send an `X-ACWM-Session` header (8–64 letters, digits or `-`).
  Each session id gets its own in-memory index store and run history, so visitors to the
  public site never see each other's data. Requests without the header use one shared
  service, which keeps `curl` and scripts working. The React frontend generates a random
  id per browser and stores it in `localStorage`. An invalid id returns
  `400 invalid_session`.
* **CORS.** Allowed origins come from `ACWM_CORS_ORIGINS` (comma-separated; defaults to the
  local Vite ports 5173 and 4173) plus `ACWM_CORS_ORIGIN_REGEX`. The regex defaults to the
  Render site `https://acwm-web*.onrender.com`. Only `GET` and `POST` with `Content-Type`
  and `X-ACWM-Session` headers are allowed.

### `GET /config`

Returns form defaults for clients: the sample repository path, budget settings, ranking
weights, expansion depth, mode labels, tokenizer encoding and provider status.

### `GET /runs?limit=10`

Returns metadata for this session's recent context builds: task, mode, file count, tokens
and latency. File contents are never included.

### `GET /health`

Returns the status, version and provider status:

```json
{"status": "ok", "version": "0.1.0",
 "providers": {"llm": "unconfigured (no LLM provider configured)",
               "semantic": "unavailable (sentence-transformers not installed)",
               "tinyfish": "disabled", "tinyfish_last_call": "not used"}}
```

### `POST /repositories/index`

```json
{"path": "examples/sample_fastapi_repo"}
```

Returns `{"repository": RepositorySummary, "report": IndexingReport}`. The
`IndexingReport` contains these fields:

* `total_discovered`, `indexed`, `skipped`;
* `excluded`: a list of `{path, reason}`;
* `file_types`, `languages`;
* `total_tokens`, `total_bytes`;
* `parse_warnings`;
* `limit_reached`, `tokenizer`, `duration_ms`.

The `repository_id` is stable for the same absolute root path.

### `GET /repositories/{repository_id}`

Query parameters:

* `include_graph=true` adds the file-level dependency graph in NetworkX node-link format.
* `include_files=true` adds every indexed file with its type, language, line count, token
  count, symbol count and parse error.
* `include_symbols=true` adds a map from path to symbols. Each symbol has `id`, `qualname`,
  `kind`, `signature`, `start_line`, `end_line` and `docstring`.

### `POST /context/build`

```json
{
  "repository_id": "a2e3af7df11aacc4",
  "task": "Add JWT authentication to the FastAPI application and create tests for protected routes.",
  "mode": "acwm",
  "token_budget": 4000,
  "reserved_response_tokens": 1500,
  "expansion_depth": 2,
  "compression": "extractive",
  "weights": {"lexical": 0.35, "filename": 0.1, "symbol": 0.15, "dependency": 0.2,
              "test": 0.1, "config": 0.05, "semantic": 0.0},
  "use_semantic": false,
  "use_llm_analysis": false,
  "include_research": false,
  "redundancy_penalty": true,
  "required_paths": ["shopapi/core/config.py"]
}
```

Only `repository_id` and `task` are required. The fields are:

| Field | Values |
|---|---|
| `mode` | `acwm` (default), `dependency`, `baseline` |
| `compression` | `extractive` (default), `llm`, `none` |
| `token_budget` | 500 to 2,000,000 |
| `required_paths` | Repository-relative paths; traversal is rejected with 403 |

The response is a full `ContextPackage`:

* `task`, `analysis`, `repository`, `configuration`;
* `items[]`, each with:
  * `path`, `kind`, `is_partial`, `line_ranges`, `symbols`;
  * `tokens`, `full_file_tokens`, `combined_score`, `scores`;
  * `reasons`, `selection_note`, `dependency_path`, `content`;
* `dependencies`, `tests`, `config_files`, `excluded`;
* `omissions`, `warnings`, `token_stats`;
* `research_findings`, `latency_ms`, `disclaimer`.

### `POST /context/compare`

The body is the same as `/context/build`, plus two optional fields:

* `relevant_paths`: ground-truth labels used to compute metrics;
* `k`: the cutoff for precision and recall (default 5).

It runs `baseline`, `dependency` and `acwm` modes with the same budget. For each method it
returns:

* `selected`, `kinds`;
* `rendered_tokens`, `usable_tokens`, `utilization`, `budget_violation`, `latency_ms`;
* `precision_at_k`, `recall_at_k`, `mrr`, `coverage`, `full_coverage`;
* `missing_relevant`.

Metrics are `null` (N/A) when no labels are supplied.

### `POST /context/export`

Provide either a package or a build request (exactly one):

```json
{"format": "markdown", "build": {"repository_id": "...", "task": "..."}}
{"format": "json", "package": { ...ContextPackage... }}
```

`format` is one of `markdown`, `json`, `txt`. The response is
`{"format", "filename", "mime_type", "content"}`. JSON content is validated against the
`ContextPackage` schema before it is returned.

### `GET /benchmarks`

Lists the labelled benchmark tasks from `benchmarks/sample_fastapi_tasks.json`.

### `POST /benchmarks/run`

```json
{"token_budget": 4000, "k": 5}
```

Indexes the sample repository and runs every task with all three methods. Returns
per-task comparisons and aggregate means. All numbers are measured at request time.

## Example session (curl)

```bash
curl -s -X POST localhost:8000/repositories/index -H "content-type: application/json" \
     -d '{"path": "examples/sample_fastapi_repo"}' | python -m json.tool | head
curl -s -X POST localhost:8000/context/export -H "content-type: application/json" \
     -d '{"format":"txt","build":{"repository_id":"<id>","task":"Fix database retry behavior"}}'
```

## Limits and safety

* Only paths under allowed roots can be indexed (`ACWM_ALLOWED_ROOTS`).
* Repository code is parsed with `ast` and is never imported or executed.
* There is no shell execution anywhere in the request path.
* Request bodies are capped at 1 MB by default.
* Long operations run in a worker thread with a timeout. On timeout the request returns
  504, but the thread is not forcibly killed.
* Indexes are held in process memory, so restarting the server requires re-indexing.
