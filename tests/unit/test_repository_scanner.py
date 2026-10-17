import os

import pytest

from app.core.config import Settings
from app.core.exceptions import InvalidRepositoryError
from app.ingestion.repository_scanner import scan_repository


def reasons(result):
    return {e.path: e.reason for e in result.report.excluded}


def test_scan_indexes_supported_files_and_reports(make_repo, tmp_settings):
    root = make_repo(
        {
            "app/main.py": "print('hi')\n",
            "README.md": "# Title\n",
            "config.yaml": "a: 1\n",
            "pyproject.toml": "[project]\nname='x'\n",
            "data.json": "{}",
            "image.png": b"\x89PNG\r\n\x1a\n\x00\x00",
        }
    )
    result = scan_repository(root, tmp_settings)
    paths = [f.path for f in result.files]
    assert paths == sorted(
        ["app/main.py", "README.md", "config.yaml", "pyproject.toml", "data.json"]
    )
    rep = result.report
    assert rep.total_discovered == 6
    assert rep.indexed == 5
    assert rep.languages["python"] == 1
    assert rep.file_types["config"] == 3
    assert rep.total_tokens == sum(f.tokens for f in result.files) > 0
    assert reasons(result)["image.png"] == "unsupported file type"


def test_excluded_directories(make_repo, tmp_settings):
    root = make_repo(
        {
            "src/a.py": "x = 1\n",
            ".git/config.py": "x = 1\n",
            ".venv/lib/site.py": "x = 1\n",
            "node_modules/pkg/index.json": "{}",
            "__pycache__/a.py": "x = 1\n",
            "build/out.py": "x = 1\n",
        }
    )
    result = scan_repository(root, tmp_settings)
    assert [f.path for f in result.files] == ["src/a.py"]
    excluded = reasons(result)
    for d in (".git/", ".venv/", "node_modules/", "__pycache__/", "build/"):
        assert d in excluded


def test_sensitive_and_secret_files_excluded_without_leaking(make_repo, tmp_settings, caplog):
    secret = "AKIA" + "QWERTYUIOPASDFGH"
    root = make_repo(
        {
            ".env": "PASSWORD=hunter2\n",
            ".env.example": "PASSWORD=change-me\n",
            "deploy/key.pem": "-----BEGIN PRIVATE KEY-----\n",
            "settings.py": f"AWS_KEY = '{secret}'\n",
            "ok.py": "x = 1\n",
        }
    )
    result = scan_repository(root, tmp_settings)
    assert {f.path for f in result.files} == {".env.example", "ok.py"}
    excluded = reasons(result)
    assert "sensitive filename" in excluded[".env"]
    assert "sensitive filename" in excluded["deploy/key.pem"]
    assert "possible secret" in excluded["settings.py"]
    assert secret not in str(result.report.model_dump())
    assert secret not in caplog.text
    assert "hunter2" not in str(result.report.model_dump())


def test_gitignore_respected(make_repo, tmp_settings):
    root = make_repo(
        {
            ".gitignore": "ignored_dir/\n*.log.py\n",
            "ignored_dir/x.py": "x = 1\n",
            "keep.py": "x = 1\n",
            "debug.log.py": "x = 1\n",
            "sub/.gitignore": "local.py\n",
            "sub/local.py": "x = 1\n",
            "sub/other.py": "x = 1\n",
        }
    )
    result = scan_repository(root, tmp_settings)
    paths = {f.path for f in result.files}
    assert "keep.py" in paths and "sub/other.py" in paths
    assert not paths & {"ignored_dir/x.py", "debug.log.py", "sub/local.py"}


def test_oversized_and_binary_files(make_repo, tmp_path):
    settings = Settings(allowed_roots=[tmp_path], max_file_bytes=1_000)
    root = make_repo(
        {
            "big.py": "x = 1\n" * 500,
            "blob.json": b'{"a": "\x00\x01\x02"}',
            "small.py": "x = 1\n",
        }
    )
    result = scan_repository(root, settings)
    excluded = reasons(result)
    assert "too large" in excluded["big.py"]
    assert excluded["blob.json"] == "binary content"
    assert [f.path for f in result.files] == ["small.py"]


def test_max_files_limit(make_repo, tmp_path):
    settings = Settings(allowed_roots=[tmp_path], max_files=2)
    root = make_repo({f"m{i}.py": "x = 1\n" for i in range(5)})
    result = scan_repository(root, settings)
    assert len(result.files) == 2
    assert result.report.limit_reached and result.report.skipped == 3


def test_empty_repository(make_repo, tmp_settings):
    root = make_repo({})
    root.mkdir(parents=True, exist_ok=True)
    result = scan_repository(root, tmp_settings)
    assert result.files == [] and result.report.indexed == 0


def test_missing_and_non_directory_paths(tmp_path, tmp_settings):
    with pytest.raises(InvalidRepositoryError):
        scan_repository(tmp_path / "missing", tmp_settings)
    f = tmp_path / "file.py"
    f.write_text("x=1")
    with pytest.raises(InvalidRepositoryError):
        scan_repository(f, tmp_settings)


def test_symlinks_outside_root_not_followed(make_repo, tmp_path, tmp_settings):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret_code.py").write_text("x = 1\n")
    root = make_repo({"inside.py": "y = 2\n"})
    try:
        os.symlink(outside / "secret_code.py", root / "link.py")
        os.symlink(outside, root / "linkdir", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links not supported in this environment")
    result = scan_repository(root, tmp_settings)
    assert [f.path for f in result.files] == ["inside.py"]
    excluded = reasons(result)
    assert "outside the repository root" in excluded["link.py"]
    assert "not followed" in excluded["linkdir/"]


def test_scan_is_deterministic(make_repo, tmp_settings):
    root = make_repo({"b.py": "x=1\n", "a/c.py": "y=2\n", "a/b.md": "# t\n"})
    first = scan_repository(root, tmp_settings)
    second = scan_repository(root, tmp_settings)
    assert [(f.path, f.sha256) for f in first.files] == [(f.path, f.sha256) for f in second.files]
