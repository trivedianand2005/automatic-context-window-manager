# TinyFish integration

**Status: implemented, mock-tested, not verified against the live service.**

No `TINYFISH_API_KEY` was available during development, so **no request to the real
TinyFish API has been made from this repository**. The adapter follows the published
documentation below and is covered by tests that use mocked HTTP responses
(`tests/unit/test_integrations.py`).

## Documentation consulted

| Page | URL | Checked |
|---|---|---|
| Search API reference | <https://docs.tinyfish.ai/search-api/reference> | 2026-10-17 |
| Fetch API reference | <https://docs.tinyfish.ai/fetch-api/reference> | 2026-10-17 |
| Agent API reference (not used) | <https://docs.tinyfish.ai/agent-api/reference> | 2026-10-17 (search summary only) |

TinyFish offers several web APIs:

* **Agent API**: goal-driven browser automation at `agent.tinyfish.ai/v1/automation/run*`.
* **Search API**: `GET https://api.search.tinyfish.ai`.
* **Fetch API**: `POST https://api.fetch.tinyfish.ai`.
* **Browser API**.

ACWM's use case is finding relevant official documentation for a coding task. The
**Search API** fits that directly, and it does not involve performing actions on
websites, so it is the only endpoint ACWM calls.

## Verified API contract (from the documentation)

* **Endpoint:** `GET https://api.search.tinyfish.ai`
* **Authentication:** `X-API-Key: <key>` header (missing or invalid key → HTTP 401).
* **Parameters used by ACWM:**
  * `query` (required): up to 8 task terms, truncated to 500 characters.
  * `purpose`: a fixed descriptive string.
  * `include_domains`: comma-separated; defaults to `fastapi.tiangolo.com`,
    `docs.pydantic.dev`, `docs.python.org`, `www.starlette.io`.
* **Response:**

  ```
  {query, results: [{position, site_name, title, snippet, url, ...}], total_results, page}
  ```

* **Documented errors:** 400, 401, 402 (credits), 403, 404, 429 (rate limit; 30 requests
  per minute default), 500, 503 (retry with backoff).

## Adapter behaviour (`app/integrations/tinyfish_client.py`)

* **Credentials** come only from the `TINYFISH_API_KEY` environment variable. They are
  never logged, and the log filter redacts `X-API-Key` values.
* **Timeout:** 20 s by default (`Settings.tinyfish_timeout_seconds`).
* **Rate limiting:** on 429 or 503 the adapter makes one bounded retry, honouring a
  numeric `Retry-After` header up to 10 s.
* **Validation:**
  * the response is validated with Pydantic models;
  * malformed JSON yields a structured error result rather than an exception;
  * results with non-HTTP(S) URLs are dropped;
  * snippets are stripped of control characters and truncated to 400 characters.
* **Attribution:** every finding records its title, URL and source (`TinyFish Search API
  (<site_name>)`), plus the provider status.
* **Safety:**
  * retrieved text is shown as *untrusted external content*;
  * it is never executed and never treated as instructions;
  * it is included in a context package only when the user enables research, and the user
    can deselect individual findings in the UI before exporting.
* **Status reporting** has four states:
  * `disabled`;
  * `mock (TINYFISH_API_KEY not set; canned offline results)`;
  * `real (configured; unverified until a request succeeds)`;
  * `real: TinyFish Search API (last request succeeded)`, set only after an actual 200
    response.

## Mock provider

`app/integrations/mock_web_research.py` returns a small set of canned links to
FastAPI and Pydantic documentation pages, matched by keyword. Every finding is labelled
`ACWM mock research (canned)`, and the package warnings state that results came from the
mock. The mock is used automatically when research is requested without a key, so the
demo works offline.

## Enabling the real service

```bash
# .env
ACWM_TINYFISH_ENABLED=true
TINYFISH_API_KEY=<your key from https://agent.tinyfish.ai/api-keys>
```

Then, in the UI, turn on **Documentation research (TinyFish)** in the Context Builder.
Through the API, send `"include_research": true` to `/context/build`. Check
`GET /health` → `providers.tinyfish_last_call` to confirm that a real request succeeded.

## Not implemented

* Fetch API page retrieval (full-page Markdown or highlights). It is a natural follow-up
  for pulling specific documentation sections into the package.
* Agent and Browser APIs. These are deliberately not used, because ACWM must not perform
  website actions.
