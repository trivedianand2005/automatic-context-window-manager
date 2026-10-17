import json

import pytest

from app.context.budget_optimizer import BudgetOptimizer, OptimizerOptions
from app.context.context_exporter import to_json, to_markdown, to_text, validate_package_json
from app.context.summarizer import (
    OUTLINE_HEADER,
    PARTIAL_HEADER,
    build_excerpt,
    python_outline,
    text_excerpt,
)
from app.context.token_counter import TokenCounter, get_token_counter, plan_budget
from app.core.config import BudgetSettings
from app.core.exceptions import BudgetExceededError
from app.core.models import Candidate, RepoFile
from app.parsing.python_parser import parse_python
from app.services.options import BuildOptions
from tests.conftest import MINI_PROJECT


def test_tiktoken_counts_and_truncate():
    counter = get_token_counter("cl100k_base")
    assert counter.method == "tiktoken"
    assert counter.count("hello world") == 2
    assert counter.count("") == 0
    long = "word " * 100
    assert counter.count(counter.truncate(long, 10)) <= 10


def test_heuristic_fallback_is_flagged(monkeypatch):
    import app.context.token_counter as tc

    monkeypatch.setattr(tc, "_load_encoder", lambda enc: None)
    counter = TokenCounter("does-not-exist")
    assert counter.method == "heuristic"
    assert any("heuristic" in w for w in counter.warnings)
    assert counter.count("abcdef") == 2


def test_plan_budget_reserves_space():
    counter = get_token_counter()
    budget = BudgetSettings(
        total_tokens=4000,
        reserved_system_tokens=300,
        reserved_response_tokens=1000,
        safety_margin_ratio=0.05,
    )
    plan = plan_budget(budget, "Add JWT auth", counter)
    assert plan.reserved_task_tokens > 0
    assert plan.usable_tokens == 4000 - 300 - 1000 - 200 - plan.reserved_task_tokens
    tiny = plan_budget(BudgetSettings(total_tokens=500, reserved_response_tokens=600), "x", counter)
    assert tiny.usable_tokens == 0


def _file(path, content):
    return RepoFile(
        path=path,
        language="python" if path.endswith(".py") else "markdown",
        file_type="source",
        size_bytes=len(content),
        sha256="h",
        tokens=get_token_counter().count(content),
        content=content,
        line_count=content.count("\n") + 1,
    )


BIG = "\n".join(
    ['"""Big module."""', "import os", ""]
    + [f"def helper_{i}(x):\n    '''Helper {i}.'''\n    return x + {i}\n" for i in range(60)]
    + ["def target_function(token):\n    '''The relevant one.'''\n    return os.path.join(token)\n"]
)


def test_python_excerpt_is_verbatim_with_line_ranges():
    info = parse_python("big.py", BIG)
    f = _file("big.py", BIG)
    ex = build_excerpt(f, info, ["big.py::target_function"], {"token"})
    assert ex.kind == "excerpt" and PARTIAL_HEADER in ex.content
    assert "def target_function(token):" in ex.content
    assert "return os.path.join(token)" in ex.content
    assert "import os" in ex.content
    sym = next(s for s in info.symbols if s.name == "target_function")
    assert (sym.start_line, sym.end_line) in ex.line_ranges
    assert "omitted" in ex.content
    assert "def helper_0(x)" in ex.content  # in the signature outline
    assert "return x + 0" not in ex.content  # body not included


def test_outline_and_text_excerpt():
    info = parse_python("big.py", BIG)
    out = python_outline(_file("big.py", BIG), info)
    assert OUTLINE_HEADER in out.content and "return" not in out.content.split("# symbols:")[1]
    md = _file("doc.md", "intro\n" * 20 + "JWT token rotation details\n" + "tail\n" * 20)
    ex = text_excerpt(md, {"jwt"})
    assert "JWT token rotation" in ex.content and ex.line_ranges == [(18, 24)]


def _optimizer(files, usable, query=frozenset({"token"}), **opts):
    counter = get_token_counter()
    plan = plan_budget(
        BudgetSettings(
            total_tokens=usable + 2000,
            reserved_system_tokens=0,
            reserved_response_tokens=2000 - 40,
            safety_margin_ratio=0,
        ),
        "t",
        counter,
    )
    modules = {p: parse_python(p, f.content) for p, f in files.items() if p.endswith(".py")}
    import networkx as nx

    return BudgetOptimizer(
        files, modules, nx.DiGraph(), counter, plan, set(query), OptimizerOptions(**opts)
    ), plan


def _cand(f, score, symbols=()):
    return Candidate(
        path=f.path,
        file_type=f.file_type,
        language=f.language,
        tokens=f.tokens,
        combined=score,
        matched_symbols=list(symbols),
    )


def test_optimizer_respects_budget_and_excerpts_large_files():
    big = _file("big.py", BIG)
    small = _file("small.py", "def token():\n    return 1\n")
    files = {"big.py": big, "small.py": small}
    opt, plan = _optimizer(files, usable=400)
    assert big.tokens > plan.usable_tokens
    res = opt.optimize([_cand(big, 0.9, ["big.py::target_function"]), _cand(small, 0.5)])
    assert res.used_tokens <= plan.usable_tokens
    kinds = {s.candidate.path: s.kind for s in res.selected}
    assert kinds["big.py"] == "excerpt" and kinds["small.py"] == "full"


def test_optimizer_threshold_and_does_not_fit_reasons():
    a = _file("a.py", "def token():\n    return 1\n")
    b = _file("b.py", "def other():\n    return 2\n")
    opt, _ = _optimizer({"a.py": a, "b.py": b}, usable=300)
    res = opt.optimize([_cand(a, 0.9), _cand(b, 0.01)])
    assert [s.candidate.path for s in res.selected] == ["a.py"]
    assert "below relevance threshold" in dict((c.path, r) for c, r in res.excluded)["b.py"]


def test_required_file_too_large_is_reported_not_silent():
    big = _file("big.md", "token words " * 2000)
    opt, _ = _optimizer({"big.md": big}, usable=100, allow_excerpts=False)
    res = opt.optimize([], required_paths=["big.md", "missing.py"])
    assert any("REQUIRED file 'big.md'" in o for o in res.omissions)
    assert any("'missing.py' is not in the index" in o for o in res.omissions)


def test_redundancy_penalty_prefers_distinct_content():
    body = "\n".join(f"value_number_{i} = compute_token_value({i})" for i in range(30))
    a, dup = _file("a.py", body), _file("copy_of_a.py", body)
    other = _file("b.py", "\n".join(f"other_value_{i} = distinct_token({i})" for i in range(30)))
    files = {"a.py": a, "copy_of_a.py": dup, "b.py": other}
    opt, _ = _optimizer(files, usable=a.tokens * 2 + 80)
    res = opt.optimize([_cand(a, 0.9), _cand(dup, 0.88), _cand(other, 0.6)])
    selected = [s.candidate.path for s in res.selected]
    assert "a.py" in selected and "b.py" in selected and "copy_of_a.py" not in selected


def test_optimizer_is_deterministic():
    files = {
        f"m{i}.py": _file(f"m{i}.py", f"def token_{i}():\n    return {i}\n" * (i + 1))
        for i in range(8)
    }
    cands = [_cand(f, 0.5 + i / 100) for i, f in enumerate(files.values())]
    runs = []
    for _ in range(3):
        opt, _ = _optimizer(files, usable=200)
        runs.append([(s.candidate.path, s.kind) for s in opt.optimize(cands).selected])
    assert runs[0] == runs[1] == runs[2]


@pytest.fixture()
def mini_package(make_repo, tmp_service):
    repo = tmp_service.index_repository(make_repo(MINI_PROJECT))
    return tmp_service.build_context(
        repo.repository_id,
        BuildOptions(task="Add token expiry to protected routes with tests", token_budget=3000),
    )


def test_package_assembly_and_exports(mini_package):
    p = mini_package
    assert p.items and p.token_stats.rendered_context_tokens <= p.token_stats.usable_tokens
    assert "pkg/routes.py" in {i.path for i in p.items}
    md = to_markdown(p)
    for heading in (
        "## Task",
        "## Token statistics",
        "## Selected files and why",
        "## Code context",
        "## Known omissions",
        "## Warnings",
        "## Limitations",
    ):
        assert heading in md
    data = json.loads(to_json(p))
    assert data["schema_version"] == "1.0"
    assert validate_package_json(to_json(p)).task == p.task
    txt = to_text(p)
    assert txt.startswith("TASK:") and "KNOWN OMISSIONS:" in txt
    for item in p.items:
        assert item.path in md and item.path in txt


def test_json_schema_validation_rejects_malformed(mini_package):
    data = json.loads(to_json(mini_package))
    data["items"][0]["kind"] = "invented"
    with pytest.raises(ValueError):
        validate_package_json(json.dumps(data))


def test_fence_escaping_for_backticks(make_repo, tmp_service):
    repo = tmp_service.index_repository(
        make_repo(
            {"doc_token.py": 's = """```python\ntoken\n```"""\n\ndef token():\n    return s\n'}
        )
    )
    p = tmp_service.build_context(repo.repository_id, BuildOptions(task="token function"))
    md = to_markdown(p)
    assert "````python" in md


def test_budget_too_small_rejected(make_repo, tmp_service):
    repo = tmp_service.index_repository(make_repo(MINI_PROJECT))
    with pytest.raises(BudgetExceededError):
        tmp_service.build_context(
            repo.repository_id,
            BuildOptions(task="token", token_budget=1000, reserved_response_tokens=900),
        )
