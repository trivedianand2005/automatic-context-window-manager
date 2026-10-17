from app.core.models import ModuleInfo
from app.parsing.import_resolver import ModuleIndex, resolve_all, resolve_import
from app.parsing.python_parser import parse_python
from app.parsing.symbol_extractor import extract_lines, module_name_for

SOURCE = '''"""Module docstring."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkg.models import User

try:
    import ujson as json
except ImportError:
    import json


@decorator
def top(a: int, b: str = "x", *args, **kw) -> bool:
    """Top-level function."""
    def inner():
        return 1
    return True


class Service(Base, metaclass=Meta):
    """A service."""

    async def run(self, user: "User") -> None:
        pass

    class Nested:
        def method(self):
            pass
'''


def test_parse_symbols_signatures_docstrings_and_lines():
    info = parse_python("pkg/service.py", SOURCE)
    assert info.parse_error is None
    assert info.module == "pkg.service"
    assert info.docstring == "Module docstring."
    by_q = {s.qualname: s for s in info.symbols}
    assert set(by_q) == {
        "top",
        "top.inner",
        "Service",
        "Service.run",
        "Service.Nested",
        "Service.Nested.method",
    }
    top = by_q["top"]
    assert top.kind == "function"
    assert top.signature == "def top(a: int, b: str='x', *args, **kw) -> bool"
    assert top.docstring == "Top-level function."
    assert top.decorators == ["decorator"]
    assert top.start_line == 16 and top.end_line == 21  # includes decorator line
    assert by_q["top.inner"].parent == "top"
    assert by_q["Service"].signature == "class Service(Base, metaclass=Meta)"
    assert by_q["Service.run"].kind == "async_method"
    assert by_q["Service.Nested.method"].kind == "method"
    assert by_q["Service.run"].id == "pkg/service.py::Service.run"


def test_import_context_flags():
    info = parse_python("pkg/service.py", SOURCE)
    imports = {(i.module, tuple(i.names)): i for i in info.imports}
    assert imports[("pkg.models", ("User",))].type_checking
    assert imports[("ujson", ())].conditional
    assert imports[("os", ())].conditional is False


def test_syntax_error_reported_not_raised():
    info = parse_python("bad.py", "def broken(:\n    pass\n")
    assert info.parse_error and "SyntaxError" in info.parse_error
    assert info.symbols == []


def test_module_names():
    assert module_name_for("pkg/__init__.py") == "pkg"
    assert module_name_for("pkg/sub/mod.py") == "pkg.sub.mod"
    assert module_name_for("stubs/x.pyi") == "stubs.x"


def test_extract_lines():
    assert extract_lines("a\nb\nc\nd", 2, 3) == "b\nc"


def _modules(files: dict[str, str]) -> list[ModuleInfo]:
    return [parse_python(p, s) for p, s in files.items()]


def test_resolve_absolute_relative_and_external():
    mods = _modules(
        {
            "pkg/__init__.py": "",
            "pkg/config.py": "X = 1\n",
            "pkg/sub/__init__.py": "",
            "pkg/sub/a.py": "from .b import thing\nfrom .. import config\nfrom ..config import X\n",
            "pkg/sub/b.py": "import os\nimport requests\nimport pkg.config\nfrom pkg import missing\n",
        }
    )
    by_src: dict[str, list] = {}
    for r in resolve_all(mods):
        by_src.setdefault(r.source_path, []).append(r)
    a_targets = {r.target_path for r in by_src["pkg/sub/a.py"]}
    assert a_targets == {"pkg/sub/b.py", "pkg/config.py"}
    b = {r.raw: r for r in by_src["pkg/sub/b.py"]}
    assert b["os"].status == "external" and b["os"].note == "stdlib"
    assert b["requests"].status == "external"
    assert b["pkg.config"].target_path == "pkg/config.py"
    assert b["from pkg import missing"].target_path == "pkg/__init__.py"  # name, not module


def test_from_import_prefers_submodule():
    mods = _modules(
        {"pkg/__init__.py": "", "pkg/routes.py": "", "main.py": "from pkg import routes\n"}
    )
    res = [r for r in resolve_all(mods) if r.source_path == "main.py"]
    assert [r.target_path for r in res] == ["pkg/routes.py"]
    assert res[0].confidence == "high"


def test_suffix_match_and_ambiguity():
    mods = _modules(
        {
            "src/app/auth.py": "",
            "src/app/__init__.py": "",
            "a/util.py": "",
            "b/util.py": "",
            "src/main.py": "import app.auth\nimport util\n",
        }
    )
    index = ModuleIndex(mods)
    main = next(m for m in mods if m.path == "src/main.py")
    auth = resolve_import(main, main.imports[0], index)[0]
    assert auth.target_path == "src/app/auth.py" and auth.confidence == "medium"
    util = resolve_import(main, main.imports[1], index)[0]
    assert util.status == "unresolved" and util.target_path is None
    assert "ambiguous" in util.note


def test_stdlib_name_not_bound_to_local_suffix():
    mods = _modules({"lib/json.py": "", "lib/__init__.py": "", "main.py": "import json\n"})
    res = [r for r in resolve_all(mods) if r.source_path == "main.py"][0]
    assert res.status == "external" and res.target_path is None


def test_type_checking_import_is_medium_confidence():
    mods = _modules(
        {
            "pkg/__init__.py": "",
            "pkg/models.py": "",
            "pkg/svc.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            "    from pkg.models import User\n",
        }
    )
    res = [r for r in resolve_all(mods) if r.target_path == "pkg/models.py"][0]
    assert res.confidence == "medium" and "TYPE_CHECKING" in res.note


def test_malformed_fixture_file(make_repo, tmp_service):
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "malformed_module.py.txt"
    root = make_repo({"pkg/broken.py": fixture.read_text(encoding="utf-8"), "pkg/ok.py": "x=1\n"})
    repo = tmp_service.index_repository(root)
    assert "pkg/broken.py" in repo.files  # still indexed for lexical search
    assert repo.modules["pkg/broken.py"].parse_error.startswith("SyntaxError at line 8")
    assert repo.modules["pkg/ok.py"].parse_error is None
