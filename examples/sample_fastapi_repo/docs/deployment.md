# Deployment

ShopAPI is deployed as a container behind a reverse proxy.

1. Set `SHOPAPI_SECRET_KEY`, `SHOPAPI_DATABASE_URL` and `SHOPAPI_ENV=production`.
2. Run `uvicorn shopapi.main:app --host 0.0.0.0 --port 8000`.
3. Configure the proxy health check to call `GET /health`.

Database connection retries are controlled by `SHOPAPI_DB_MAX_RETRIES`.
