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
