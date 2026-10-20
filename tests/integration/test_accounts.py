"""Accounts (email/password + GitHub), login enforcement and per-user saved packages.

Uses a temporary SQLite database by default. Set ACWM_TEST_DATABASE_URL to run the same
tests against PostgreSQL (CI does this with a Postgres service container).
"""

import os
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import SAMPLE_REPO_PATH, Settings
from app.services.accounts import hash_password, verify_password
from app.storage.database import Base

TASK = "Add JWT authentication to the FastAPI application and create tests for protected routes."


def make_client(tmp_path, **overrides) -> TestClient:
    url = os.getenv("ACWM_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'acwm.db'}"
    settings = Settings(
        allowed_roots=[SAMPLE_REPO_PATH.parent],
        database_url=url,
        jwt_secret="test-secret-" + "x" * 32,
        frontend_url="https://web.example",
        public_api_url="https://api.example",
        **overrides,
    )
    app = create_app(settings)
    engine = app.state.accounts.db.engine
    Base.metadata.drop_all(engine)  # clean slate (matters for a shared Postgres)
    Base.metadata.create_all(engine)
    return TestClient(app)


@pytest.fixture()
def client(tmp_path):
    return make_client(tmp_path)


def signup(client, email="anand@example.com", password="correct-horse", name="Anand"):
    r = client.post(
        "/auth/signup", json={"email": email, "password": password, "display_name": name}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


def build_package(client, headers):
    rid = client.post("/repositories/index", json={"path": str(SAMPLE_REPO_PATH)}, headers=headers)
    assert rid.status_code == 200, rid.text
    r = client.post(
        "/context/build",
        headers=headers,
        json={
            "repository_id": rid.json()["repository"]["repository_id"],
            "task": TASK,
            "token_budget": 4000,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ passwords
def test_password_hashing():
    h1, h2 = hash_password("s3cret-pass"), hash_password("s3cret-pass")
    assert h1 != h2 and "s3cret-pass" not in h1 and h1.startswith("scrypt$")
    assert verify_password("s3cret-pass", h1)
    assert not verify_password("wrong-pass", h1)
    assert not verify_password("x", None) and not verify_password("x", "garbage")


# ------------------------------------------------------------------- email flow
def test_signup_me_login_roundtrip(client):
    headers, user = signup(client)
    assert user["email"] == "anand@example.com" and user["display_name"] == "Anand"
    me = client.get("/auth/me", headers=headers).json()
    assert me["id"] == user["id"]
    login = client.post(
        "/auth/login", json={"email": "ANAND@example.com ", "password": "correct-horse"}
    )
    assert login.status_code == 200 and login.json()["user"]["id"] == user["id"]


@pytest.mark.parametrize(
    "body, status, code",
    [
        ({"email": "not-an-email", "password": "longenough"}, 422, "invalid_input"),
        ({"email": "a@example.com", "password": "short"}, 422, "invalid_input"),
    ],
)
def test_signup_validation(client, body, status, code):
    r = client.post("/auth/signup", json=body)
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_duplicate_email(client):
    signup(client)
    r = client.post("/auth/signup", json={"email": "anand@example.com", "password": "another-pass"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "account_exists"


def test_wrong_password_and_unknown_email_look_the_same(client):
    signup(client)
    a = client.post("/auth/login", json={"email": "anand@example.com", "password": "nope-nope"})
    b = client.post("/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


def test_login_rate_limit(client):
    signup(client)
    for _ in range(10):
        assert (
            client.post(
                "/auth/login", json={"email": "anand@example.com", "password": "bad-guess"}
            ).status_code
            == 401
        )
    r = client.post("/auth/login", json={"email": "anand@example.com", "password": "correct-horse"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


def test_bad_tokens_rejected(client):
    _, user = signup(client)
    secret = "test-secret-" + "x" * 32
    now = datetime.now(UTC)
    expired = jwt.encode(
        {"sub": str(user["id"]), "iss": "acwm", "typ": "access", "exp": now - timedelta(minutes=1)},
        secret,
        algorithm="HS256",
    )
    forged = jwt.encode(
        {"sub": str(user["id"]), "iss": "acwm", "typ": "access", "exp": now + timedelta(hours=1)},
        "someone-elses-secret-" + "y" * 20,
        algorithm="HS256",
    )
    for token, fragment in ((expired, "expired"), (forged, "Invalid"), ("garbage", "Invalid")):
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401 and fragment in r.json()["error"]["message"]
    assert client.get("/auth/me").status_code == 401


# --------------------------------------------------------------- require_auth
def test_require_auth_protects_working_endpoints(tmp_path):
    c = make_client(tmp_path, require_auth=True)
    for path in ("/health", "/config", "/benchmarks", "/auth/providers"):
        assert c.get(path).status_code == 200, path
    r = c.post("/repositories/index", json={"path": str(SAMPLE_REPO_PATH)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"
    assert c.get("/runs").status_code == 401
    headers, _ = signup(c)
    assert (
        c.post(
            "/repositories/index", json={"path": str(SAMPLE_REPO_PATH)}, headers=headers
        ).status_code
        == 200
    )
    assert c.get("/auth/providers").json()["require_auth"] is True


def test_users_have_isolated_workspaces(client):
    a, _ = signup(client, "a@example.com")
    b, _ = signup(client, "b@example.com")
    rid = client.post(
        "/repositories/index", json={"path": str(SAMPLE_REPO_PATH)}, headers=a
    ).json()["repository"]["repository_id"]
    assert (
        client.post(
            "/context/build", headers=a, json={"repository_id": rid, "task": TASK}
        ).status_code
        == 200
    )
    r = client.post("/context/build", headers=b, json={"repository_id": rid, "task": TASK})
    assert r.status_code == 404  # B never indexed it; A's workspace is invisible to B
    assert len(client.get("/runs", headers=a).json()) == 1
    assert client.get("/runs", headers=b).json() == []


# ------------------------------------------------------------- saved packages
def test_saved_packages_crud_and_isolation(client):
    a, _ = signup(client, "a@example.com")
    b, _ = signup(client, "b@example.com")
    pkg = build_package(client, a)
    saved = client.post("/packages", headers=a, json={"title": "JWT context", "package": pkg})
    assert saved.status_code == 201, saved.text
    s = saved.json()
    assert s["title"] == "JWT context" and s["item_count"] == len(pkg["items"])
    assert s["rendered_tokens"] == pkg["token_stats"]["rendered_context_tokens"]
    listing = client.get("/packages", headers=a).json()
    assert [p["id"] for p in listing] == [s["id"]]
    full = client.get(f"/packages/{s['id']}", headers=a).json()
    assert full["package"]["task"] == TASK and len(full["package"]["items"]) == len(pkg["items"])
    # Another user can neither see, open nor delete it.
    assert client.get("/packages", headers=b).json() == []
    assert client.get(f"/packages/{s['id']}", headers=b).status_code == 404
    assert client.delete(f"/packages/{s['id']}", headers=b).status_code == 404
    # Owner deletes it.
    assert client.delete(f"/packages/{s['id']}", headers=a).status_code == 204
    assert client.get(f"/packages/{s['id']}", headers=a).status_code == 404
    assert client.get("/packages").status_code == 401


def test_package_quota_and_validation(tmp_path):
    c = make_client(tmp_path, max_saved_packages=2)
    h, _ = signup(c)
    pkg = build_package(c, h)
    for _ in range(2):
        assert c.post("/packages", headers=h, json={"package": pkg}).status_code == 201
    r = c.post("/packages", headers=h, json={"package": pkg})
    assert r.status_code == 409 and r.json()["error"]["code"] == "quota_exceeded"
    bad = dict(pkg, items="not a list")
    assert c.post("/packages", headers=h, json={"package": bad}).status_code == 422
    # Untitled packages default to the task text.
    assert c.get("/packages", headers=h).json()[0]["title"] == TASK


# ------------------------------------------------------------------- GitHub
def test_github_not_configured(client):
    assert client.get("/auth/providers").json()["github"] is False
    r = client.get("/auth/github/login", follow_redirects=False)
    assert r.status_code == 501 and r.json()["error"]["code"] == "not_configured"


def _github_mock(user_id=4242, login="octo-anand"):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/login/oauth/access_token":
            body = parse_qs(request.content.decode())
            if body.get("code") != ["good-code"] or not body.get("code_verifier"):
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": "gho_test", "token_type": "bearer"})
        if request.url.path == "/user":
            assert request.headers["Authorization"] == "Bearer gho_test"
            return httpx.Response(200, json={"id": user_id, "login": login, "name": "Octo Anand"})
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


def _start_github(c):
    r = c.get("/auth/github/login", follow_redirects=False)
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    q = parse_qs(url.query)
    return url, q, r.cookies.get("acwm_gh_state")


def test_github_login_flow(tmp_path):
    c = make_client(tmp_path, github_client_id="gh-client", github_client_secret="gh-secret")
    transport, calls = _github_mock()
    c.app.state.accounts._github_transport = transport
    assert c.get("/auth/providers").json()["github"] is True

    url, q, cookie = _start_github(c)
    assert url.netloc == "github.com" and url.path == "/login/oauth/authorize"
    assert q["client_id"] == ["gh-client"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["https://api.example/auth/github/callback"]
    assert cookie and q["state"]

    r = c.get(
        "/auth/github/callback",
        params={"code": "good-code", "state": q["state"][0]},
        cookies={"acwm_gh_state": cookie},
        follow_redirects=False,
    )
    loc = r.headers["location"]
    assert r.status_code == 302 and loc.startswith("https://web.example/#auth_token=")
    token = unquote(loc.split("#auth_token=", 1)[1])
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["github_login"] == "octo-anand" and me["email"] is None
    assert any(req.url.path == "/login/oauth/access_token" for req in calls)

    # Logging in again with the same GitHub account returns the same user.
    _, q2, cookie2 = _start_github(c)
    r2 = c.get(
        "/auth/github/callback",
        params={"code": "good-code", "state": q2["state"][0]},
        cookies={"acwm_gh_state": cookie2},
        follow_redirects=False,
    )
    token2 = unquote(r2.headers["location"].split("#auth_token=", 1)[1])
    assert c.get("/auth/me", headers={"Authorization": f"Bearer {token2}"}).json()["id"] == me["id"]


@pytest.mark.parametrize("case", ["no_cookie", "wrong_state", "cancelled", "bad_code"])
def test_github_callback_failures_redirect_with_error(tmp_path, case):
    c = make_client(tmp_path, github_client_id="gh-client", github_client_secret="gh-secret")
    c.app.state.accounts._github_transport, _ = _github_mock()
    _, q, cookie = _start_github(c)
    params = {"code": "good-code", "state": q["state"][0]}
    cookies = {"acwm_gh_state": cookie}
    if case == "no_cookie":
        cookies = {}
    elif case == "wrong_state":
        params["state"] = "attacker-state"
    elif case == "cancelled":
        params = {"error": "access_denied", "state": q["state"][0]}
    elif case == "bad_code":
        params["code"] = "stolen-code"
    r = c.get("/auth/github/callback", params=params, cookies=cookies, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://web.example/#auth_error=")
    assert "auth_token" not in r.headers["location"]
