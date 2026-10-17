"""Path and secret-handling safeguards.

These are defence-in-depth checks for a *local* developer tool. They are not a
sandbox and do not make ACWM safe to expose as a multi-tenant service.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path, PurePosixPath

from app.core.exceptions import PathSecurityError

SENSITIVE_FILENAMES = {
    ".env",
    ".envrc",
    ".netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "service-account.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
}
SENSITIVE_GLOBS = [
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.kdbx",
    "*secret*.json",
    "*credential*",
    "*.tfstate",
]
# Template files intentionally contain placeholders, so they are allowed.
ALLOWED_TEMPLATE_NAMES = {".env.example", ".env.sample", ".env.template"}

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{10,}\b")),
    ("Anthropic/OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_\-]{32,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    (
        "hard-coded credential assignment",
        re.compile(
            r"""(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|password|passwd)\b"""
            r"""\s*[:=]\s*["']([A-Za-z0-9+/_\-]{24,})["']"""
        ),
    ),
]
_REDACT_PATTERNS = [p for _, p in _SECRET_PATTERNS] + [
    re.compile(r"(?i)(x-api-key|authorization|api[_-]?key)(\s*[:=]\s*)(\S+)"),
]


def is_sensitive_filename(rel_path: str) -> bool:
    name = PurePosixPath(rel_path).name.lower()
    if name in ALLOWED_TEMPLATE_NAMES:
        return False
    if name in SENSITIVE_FILENAMES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in SENSITIVE_GLOBS)


def detect_secret(text: str) -> str | None:
    """Return a *label* for the first likely secret found (never the secret itself)."""
    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            return label
    return None


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in _REDACT_PATTERNS:
        if pattern.groups >= 3:
            redacted = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def validate_repository_path(raw_path: str | Path, allowed_roots: list[Path]) -> Path:
    """Resolve a user-supplied path and ensure it lies inside an allowed root."""
    if raw_path is None or not str(raw_path).strip():
        raise PathSecurityError("Repository path is empty.")
    text = str(raw_path).strip()
    if "\x00" in text:
        raise PathSecurityError("Repository path contains a null byte.")
    try:
        resolved = Path(text).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise PathSecurityError(f"Could not resolve repository path: {exc}") from exc
    if not any(is_within(resolved, root) for root in allowed_roots):
        raise PathSecurityError(
            "Repository path is outside the allowed roots. Add its parent directory to "
            "ACWM_ALLOWED_ROOTS to permit it.",
            details={"allowed_roots": [str(r) for r in allowed_roots]},
        )
    return resolved


def safe_join(root: Path, rel_path: str) -> Path:
    """Join a repository-relative path to ``root``, rejecting traversal and absolute paths."""
    if not rel_path or "\x00" in rel_path:
        raise PathSecurityError("Invalid relative path.")
    candidate = PurePosixPath(rel_path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or ":" in candidate.parts[0]:
        raise PathSecurityError("Path traversal or absolute path rejected.")
    full = (root / Path(*candidate.parts)).resolve()
    if not is_within(full, root):
        raise PathSecurityError("Resolved path escapes the repository root.")
    return full
