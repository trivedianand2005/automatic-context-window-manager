"""Map files to a language and a coarse file type."""

from __future__ import annotations

from pathlib import PurePosixPath

from app.core.models import FileType

EXTENSION_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".env.example": "dotenv",
}
SPECIAL_FILENAMES = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    ".env.example": "dotenv",
    ".env.sample": "dotenv",
    ".env.template": "dotenv",
    "requirements.txt": "requirements",
    ".gitignore": "gitignore",
}
CONFIG_LANGUAGES = {
    "json",
    "yaml",
    "toml",
    "ini",
    "dotenv",
    "requirements",
    "dockerfile",
    "makefile",
}
CONFIG_NAME_HINTS = ("config", "settings", "conf")


def detect_language(rel_path: str) -> str | None:
    """Return the language for supported files, or ``None`` if unsupported."""
    path = PurePosixPath(rel_path)
    name = path.name.lower()
    if name in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[name]
    return EXTENSION_LANGUAGES.get(path.suffix.lower())


def is_test_path(rel_path: str) -> bool:
    path = PurePosixPath(rel_path)
    name = path.name.lower()
    parts = {p.lower() for p in path.parts[:-1]}
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or "tests" in parts
        or "test" in parts
    )


def detect_file_type(rel_path: str, language: str) -> FileType:
    stem = PurePosixPath(rel_path).stem.lower()
    if language == "python":
        if is_test_path(rel_path):
            return "test"
        if any(hint in stem for hint in CONFIG_NAME_HINTS):
            return "config"
        return "source"
    if language in CONFIG_LANGUAGES:
        return "config"
    if language in {"markdown", "restructuredtext", "text"}:
        return "docs"
    return "other"
