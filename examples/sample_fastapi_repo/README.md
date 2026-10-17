# ShopAPI (ACWM demonstration repository)

A deliberately small FastAPI service used to demonstrate ACWM's dependency-aware
context selection. All data is dummy demonstration data; there are no real credentials.

## Layout

- `shopapi/main.py` - application factory, router registration
- `shopapi/api/routes/` - `public` (health, products), `auth` (login/logout),
  `orders` and `users` (protected: require a bearer session token)
- `shopapi/api/dependencies.py` - `get_current_user` and service dependencies
- `shopapi/services/` - `AuthService` (opaque session tokens), `OrderService`
- `shopapi/core/` - settings, errors and exception handlers, password hashing
- `shopapi/db/` - in-memory database with connection retry, repositories
- `shopapi/utils/retry.py` - retry with backoff (has a known linear-backoff bug)
- `shopapi/analytics/` - offline reporting and LLM *token usage* billing analytics
  (lexically similar to "auth token" tasks but unrelated)

## Run the tests

```bash
cd examples/sample_fastapi_repo
python -m pytest
```

## Known gaps (used as benchmark tasks)

- Authentication uses opaque server-side tokens; there is no JWT support.
- `retry_with_backoff` grows delays linearly instead of exponentially.
- `OrderCreate.quantity` is not validated.
- Only `ShopAPIError` subclasses get structured error responses.
