import pytest

from app.core.exceptions import PathSecurityError
from app.utils.security import (
    detect_secret,
    is_sensitive_filename,
    redact_secrets,
    safe_join,
    validate_repository_path,
)


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "config/.env.production",
        "id_rsa",
        "server.pem",
        "tls.key",
        "secrets.json",
        "aws_credentials",
        "prod.tfstate",
    ],
)
def test_sensitive_filenames_detected(name):
    assert is_sensitive_filename(name)


@pytest.mark.parametrize("name", [".env.example", "app/config.py", "README.md", "keys.py"])
def test_regular_files_not_sensitive(name):
    assert not is_sensitive_filename(name)


def test_detect_secret_returns_label_not_value():
    key = "AKIA" + "ABCDEFGHIJKLMNOP"
    label = detect_secret(f"aws = '{key}'")
    assert label == "AWS access key id"
    assert key not in label


def test_detect_private_key_and_assignment():
    assert detect_secret("-----BEGIN RSA PRIVATE KEY-----\nabc") == "private key block"
    assert detect_secret('API_KEY = "abcdefghijklmnopqrstuvwxyz123456"') is not None
    assert detect_secret('secret_key = os.getenv("X", "dev-only-placeholder")') is None


def test_redact_secrets_hides_api_key_headers():
    text = "X-API-Key: supersecretvalue123 and sk-" + "a" * 40
    out = redact_secrets(text)
    assert "supersecretvalue123" not in out
    assert "a" * 40 not in out
    assert "[REDACTED]" in out


def test_validate_repository_path_rejects_outside_root(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(PathSecurityError):
        validate_repository_path(tmp_path / "other", [allowed])
    with pytest.raises(PathSecurityError):
        validate_repository_path(str(allowed / ".." / "other"), [allowed])
    assert validate_repository_path(allowed, [allowed]) == allowed.resolve()


@pytest.mark.parametrize("bad", ["", "   ", "abc\x00def"])
def test_validate_repository_path_rejects_malformed(bad, tmp_path):
    with pytest.raises(PathSecurityError):
        validate_repository_path(bad, [tmp_path])


@pytest.mark.parametrize("rel", ["../etc/passwd", "a/../../b", "/etc/passwd", "C:/Windows"])
def test_safe_join_rejects_traversal(rel, tmp_path):
    with pytest.raises(PathSecurityError):
        safe_join(tmp_path, rel)


def test_safe_join_accepts_relative(tmp_path):
    assert safe_join(tmp_path, "pkg/mod.py") == (tmp_path / "pkg" / "mod.py").resolve()
