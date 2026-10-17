"""Shared fixtures: isolated temporary repositories and services."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import SAMPLE_REPO_PATH, Settings
from app.services.acwm_service import ACWMService


def write_files(root: Path, files: dict[str, str | bytes]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


@pytest.fixture()
def make_repo(tmp_path):
    def _make(files: dict[str, str | bytes], name: str = "repo") -> Path:
        return write_files(tmp_path / name, files)

    return _make


@pytest.fixture()
def tmp_settings(tmp_path) -> Settings:
    return Settings(allowed_roots=[tmp_path])


@pytest.fixture()
def tmp_service(tmp_settings) -> ACWMService:
    return ACWMService(tmp_settings)


@pytest.fixture(scope="session")
def sample_service() -> ACWMService:
    return ACWMService(Settings(allowed_roots=[SAMPLE_REPO_PATH.parent]))


@pytest.fixture(scope="session")
def sample_repo(sample_service):
    return sample_service.index_repository(SAMPLE_REPO_PATH)


MINI_PROJECT = {
    "pkg/__init__.py": "",
    "pkg/config.py": '"""Settings."""\nSECRET_NAME = "jwt-secret-name"\nTOKEN_TTL = 30\n',
    "pkg/auth.py": (
        '"""Authentication helpers."""\n'
        "from pkg.config import TOKEN_TTL\n\n\n"
        "def create_token(user: str) -> str:\n"
        '    """Create an auth token for a user."""\n'
        "    return f'{user}:{TOKEN_TTL}'\n\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    return ':' in token\n"
    ),
    "pkg/routes.py": (
        "from pkg.auth import verify_token\n\n\n"
        "def protected_route(token: str) -> dict:\n"
        "    if not verify_token(token):\n"
        "        raise PermissionError('denied')\n"
        "    return {'ok': True}\n"
    ),
    "pkg/unrelated.py": "def add(a, b):\n    return a + b\n",
    "tests/test_auth.py": (
        "from pkg.auth import create_token, verify_token\n\n\n"
        "def test_roundtrip():\n    assert verify_token(create_token('u'))\n"
    ),
    "README.md": "# Mini project\n\nA tiny project used in ACWM tests.\n",
}
