# Changelog

## 0.9.0
- Added token usage analytics for partner billing (prompt/completion tokens per day).
- Added token-bucket rate limiter utility (not yet enabled on routes).
- Planned: JWT authentication for protected routes, replacing opaque session tokens.
- Planned: request validation for order quantities.

## 0.8.0
- Database connection retry: connection attempts are retried with backoff
  (`SHOPAPI_DB_MAX_RETRIES`). Known issue: backoff is linear, not exponential.
- Improved API error handling: domain errors now return `{"error": {...}}` bodies.

## 0.7.0
- Orders API: list and place orders (protected routes, bearer session token required).
- `/users/me` profile endpoint (protected).
- Login and logout endpoints using server-side session tokens.

## 0.6.0
- Payment gateway client with idempotency keys; charges are never retried.
- Notification templates for login alerts and password reset e-mails.

## 0.5.0
- Initial public routes: health check and product listing.
- Settings loaded from environment variables.
