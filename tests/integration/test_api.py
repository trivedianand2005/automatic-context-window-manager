import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import SAMPLE_REPO_PATH, Settings

TASK = "Fix database retry behavior and add regression tests."


@pytest.fixture(scope="module")
def client():
    settings = Settings(allowed_roots=[SAMPLE_REPO_PATH.parent], api_max_request_bytes=200_000)
    return TestClient(create_app(settings))


@pytest.fixture(scope="module")
def repo_id(client):
    r = client.post("/repositories/index", json={"path": str(SAMPLE_REPO_PATH)})
    assert r.status_code == 200, r.text
    return r.json()["repository"]["repository_id"]


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and {"llm", "semantic", "tinyfish"} <= set(body["providers"])


def test_openapi_documents_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in (
        "/health",
        "/repositories/index",
        "/repositories/{repository_id}",
        "/context/build",
        "/context/compare",
        "/context/export",
        "/benchmarks",
        "/benchmarks/run",
    ):
        assert p in paths


def test_index_and_get_repository(client, repo_id):
    r = client.get(
        f"/repositories/{repo_id}", params={"include_graph": True, "include_symbols": True}
    )
    body = r.json()
    assert r.status_code == 200
    assert body["repository"]["indexed_files"] >= 40
    assert body["graph"]["nodes"] and "shopapi/db/database.py" in body["symbols"]


@pytest.mark.parametrize(
    "path, status, code",
    [
        ("C:/Windows" if __import__("os").name == "nt" else "/etc", 403, "path_not_allowed"),
        (str(SAMPLE_REPO_PATH / ".." / ".." / ".."), 403, "path_not_allowed"),
        (str(SAMPLE_REPO_PATH / "does-not-exist"), 400, "invalid_repository"),
        (str(SAMPLE_REPO_PATH / "README.md"), 400, "invalid_repository"),
    ],
)
def test_index_invalid_paths(client, path, status, code):
    r = client.post("/repositories/index", json={"path": path})
    assert r.status_code == status
    assert r.json()["error"]["code"] == code


def test_index_validation_error(client):
    r = client.post("/repositories/index", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_unknown_repository_404(client):
    assert client.get("/repositories/unknown").status_code == 404
    r = client.post("/context/build", json={"repository_id": "unknown", "task": TASK})
    assert r.status_code == 404


def test_build_context(client, repo_id):
    r = client.post(
        "/context/build", json={"repository_id": repo_id, "task": TASK, "token_budget": 4000}
    )
    assert r.status_code == 200
    body = r.json()
    assert (
        body["items"]
        and body["token_stats"]["rendered_context_tokens"] <= body["token_stats"]["usable_tokens"]
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"task": "  "},
        {"task": TASK, "token_budget": 10},
        {"task": TASK, "mode": "magic"},
        {"task": TASK, "repository_id": "../etc"},
    ],
)
def test_build_invalid_requests(client, repo_id, payload):
    body = {"repository_id": repo_id, **payload}
    assert client.post("/context/build", json=body).status_code == 422


def test_build_required_path_traversal_rejected(client, repo_id):
    r = client.post(
        "/context/build",
        json={"repository_id": repo_id, "task": TASK, "required_paths": ["../../secret.py"]},
    )
    assert r.status_code == 403


def test_compare(client, repo_id):
    r = client.post(
        "/context/compare",
        json={
            "repository_id": repo_id,
            "task": TASK,
            "token_budget": 4000,
            "relevant_paths": ["shopapi/db/database.py", "shopapi/utils/retry.py"],
        },
    )
    assert r.status_code == 200
    methods = r.json()["methods"]
    assert [m["mode"] for m in methods] == ["baseline", "dependency", "acwm"]


@pytest.mark.parametrize(
    "fmt, marker",
    [("markdown", "# ACWM Context Package"), ("json", '"schema_version"'), ("txt", "TASK:")],
)
def test_export_formats(client, repo_id, fmt, marker):
    r = client.post(
        "/context/export", json={"format": fmt, "build": {"repository_id": repo_id, "task": TASK}}
    )
    assert r.status_code == 200
    assert marker in r.json()["content"]


def test_export_from_package_and_invalid(client, repo_id):
    pkg = client.post("/context/build", json={"repository_id": repo_id, "task": TASK}).json()
    r = client.post("/context/export", json={"format": "txt", "package": pkg})
    assert r.status_code == 200
    r = client.post("/context/export", json={"format": "txt"})
    assert r.status_code == 422


def test_request_size_limit(client):
    r = client.post(
        "/context/build", content=b"x" * 300_000, headers={"content-type": "application/json"}
    )
    assert r.status_code == 413 and r.json()["error"]["code"] == "request_too_large"


def test_benchmarks(client):
    listing = client.get("/benchmarks").json()
    assert len(listing["tasks"]) == 5
    r = client.post("/benchmarks/run", json={"token_budget": 4000})
    assert r.status_code == 200 and set(r.json()["aggregate"]) == {"baseline", "dependency", "acwm"}


SAMPLE_PATH = {"path": str(SAMPLE_REPO_PATH)}


def test_config_and_runs(client):
    cfg = client.get("/config").json()
    assert cfg["sample_repository_path"].endswith("sample_fastapi_repo")
    names = {r["path"].replace("\\", "/").rsplit("/", 1)[-1] for r in cfg["example_repositories"]}
    assert {"sample_fastapi_repo", "sample_library_repo"} <= names
    assert set(cfg["modes"]) == {"acwm", "dependency", "baseline"}
    assert cfg["weights"]["lexical"] > 0 and cfg["budget"]["total_tokens"] > 0
    headers = {"X-ACWM-Session": "runs-session-0001"}
    rid = client.post("/repositories/index", json=SAMPLE_PATH, headers=headers).json()[
        "repository"
    ]["repository_id"]
    client.post("/context/build", json={"repository_id": rid, "task": TASK}, headers=headers)
    runs = client.get("/runs", headers=headers).json()
    assert len(runs) == 1 and runs[0]["task"] == TASK
    assert client.get("/runs", headers={"X-ACWM-Session": "other-session-01"}).json() == []


def test_sessions_are_isolated(client):
    a = {"X-ACWM-Session": "session-aaaa-0001"}
    b = {"X-ACWM-Session": "session-bbbb-0002"}
    rid = client.post("/repositories/index", json=SAMPLE_PATH, headers=a).json()["repository"][
        "repository_id"
    ]
    assert client.get(f"/repositories/{rid}", headers=a).status_code == 200
    r = client.post("/context/build", json={"repository_id": rid, "task": TASK}, headers=b)
    assert r.status_code == 404  # session B never indexed it


@pytest.mark.parametrize("bad", ["short", "has spaces in it", "x" * 65, "semi;colon-1234"])
def test_invalid_session_header(client, bad):
    r = client.get("/runs", headers={"X-ACWM-Session": bad})
    assert r.status_code in (400, 422)
    assert r.json()["error"]["code"] in ("invalid_session", "validation_error")


def test_repository_file_and_symbol_details(client):
    h = {"X-ACWM-Session": "detail-session-01"}
    rid = client.post("/repositories/index", json=SAMPLE_PATH, headers=h).json()["repository"][
        "repository_id"
    ]
    body = client.get(
        f"/repositories/{rid}", params={"include_files": True, "include_symbols": True}, headers=h
    ).json()
    files = {f["path"]: f for f in body["files"]}
    assert files["shopapi/services/auth_service.py"]["symbol_count"] >= 5
    sym = next(
        s
        for s in body["symbols"]["shopapi/services/auth_service.py"]
        if s["qualname"] == "AuthService.issue_token"
    )
    assert sym["kind"] == "method" and sym["start_line"] < sym["end_line"]


def test_cors_preflight(client):
    allowed = client.options(
        "/context/build",
        headers={
            "Origin": "https://acwm-web.onrender.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-acwm-session",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://acwm-web.onrender.com"
    local = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert local.headers["access-control-allow-origin"] == "http://localhost:5173"
    evil = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in evil.headers
