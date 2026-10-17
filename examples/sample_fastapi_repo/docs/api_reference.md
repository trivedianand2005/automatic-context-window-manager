# ShopAPI HTTP reference

All error responses use the shape `{"error": {"code": "...", "message": "..."}}`.

## Public routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Liveness check |
| GET | `/products?limit=20` | none | List products (limit capped by settings) |

## Authentication routes

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | none | Exchange username/password for a bearer session token |
| POST | `/auth/logout` | bearer token | Revoke the current session token |

Request body for login: `{"username": "...", "password": "..."}`.
Response: `{"access_token": "...", "token_type": "bearer", "expires_in": 1800}`.

## Protected routes

Protected routes require `Authorization: Bearer <token>`. Missing or invalid tokens
return `401 not_authenticated`.

| Method | Path | Description |
|---|---|---|
| GET | `/orders` | List the current user's orders |
| POST | `/orders` | Place an order: `{"product_id": 1, "quantity": 2}` |
| GET | `/users/me` | Current user's profile |

## Errors

| Status | Code | When |
|---|---|---|
| 401 | `not_authenticated` | Missing, invalid or expired token; bad credentials |
| 404 | `not_found` | Unknown product |
| 422 | (FastAPI default) | Request validation errors (not yet customised) |
| 503 | `database_unavailable` | Database connection retries exhausted |
