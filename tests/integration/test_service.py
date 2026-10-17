import pytest

from app.core.exceptions import PathSecurityError, RepositoryNotFoundError
from app.services.options import BuildOptions

JWT_TASK = (
    "Add JWT authentication to the FastAPI application and create tests for protected routes."
)


def test_sample_repository_indexing(sample_repo):
    rep = sample_repo.report
    assert rep.indexed >= 40 and rep.total_tokens > 5000
    assert rep.languages["python"] >= 30
    assert not [w for w in rep.parse_warnings if "SyntaxError" in w]
    edges = {(u, v) for u, v, d in sample_repo.graph.edges(data=True) if d["relation"] == "imports"}
    assert ("file:shopapi/api/routes/orders.py", "file:shopapi/api/dependencies.py") in edges
    assert ("file:shopapi/api/dependencies.py", "file:shopapi/services/auth_service.py") in edges


@pytest.mark.parametrize("mode", ["baseline", "dependency", "acwm"])
def test_all_modes_respect_budget(sample_service, sample_repo, mode):
    p = sample_service.build_context(
        sample_repo.repository_id, BuildOptions(task=JWT_TASK, mode=mode, token_budget=4000)
    )
    st = p.token_stats
    assert 0 < st.rendered_context_tokens <= st.usable_tokens
    assert st.usable_tokens == st.total_budget - (
        st.reserved_system_tokens
        + st.reserved_task_tokens
        + st.reserved_response_tokens
        + st.safety_margin_tokens
    )


def test_acwm_follows_dependencies_from_routes(sample_service, sample_repo):
    p = sample_service.build_context(
        sample_repo.repository_id, BuildOptions(task=JWT_TASK, token_budget=8000)
    )
    selected = {i.path for i in p.items}
    assert {
        "shopapi/api/dependencies.py",
        "shopapi/services/auth_service.py",
        "shopapi/core/config.py",
        "tests/test_auth.py",
    } <= selected
    dep_item = next(i for i in p.items if i.path == "shopapi/services/auth_service.py")
    assert dep_item.dependency_path and dep_item.reasons
    assert (
        "shopapi/analytics/token_usage.py" not in selected
        or next(i for i in p.items if i.path == "shopapi/analytics/token_usage.py").combined_score
        < dep_item.combined_score
    )


def test_context_build_is_deterministic(sample_service, sample_repo):
    opts = BuildOptions(task=JWT_TASK, token_budget=4000)
    a = sample_service.build_context(sample_repo.repository_id, opts)
    b = sample_service.build_context(sample_repo.repository_id, opts)
    assert [(i.path, i.kind, i.tokens) for i in a.items] == [
        (i.path, i.kind, i.tokens) for i in b.items
    ]


def test_compare_with_labels(sample_service, sample_repo):
    _, tasks = sample_service.load_benchmark()
    t = tasks[0]
    cmp = sample_service.compare(
        sample_repo.repository_id, BuildOptions(task=t.task, token_budget=4000), t.relevant
    )
    assert [m.mode for m in cmp.methods] == ["baseline", "dependency", "acwm"]
    usable = {m.usable_tokens for m in cmp.methods}
    assert len(usable) == 1  # identical budget for all methods
    for m in cmp.methods:
        assert not m.budget_violation
        assert m.coverage is not None and 0 <= m.coverage <= 1


def test_compare_without_labels_reports_na(sample_service, sample_repo):
    cmp = sample_service.compare(sample_repo.repository_id, BuildOptions(task=JWT_TASK))
    assert all(m.precision_at_k is None and m.coverage is None for m in cmp.methods)
    assert any("N/A" in n for n in cmp.notes)


def test_benchmark_run(sample_service):
    report = sample_service.run_benchmarks(token_budget=4000)
    assert len(report.tasks) == 5
    assert set(report.aggregate) == {"baseline", "dependency", "acwm"}
    for agg in report.aggregate.values():
        assert agg["budget_violations"] == 0
        assert 0 <= agg["coverage"] <= 1


def test_llm_compression_falls_back_without_provider(sample_service, sample_repo, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = sample_service.build_context(
        sample_repo.repository_id, BuildOptions(task=JWT_TASK, token_budget=3000, compression="llm")
    )
    assert any("LLM requested" in w for w in p.warnings)
    assert all(i.kind != "summary" for i in p.items)
    assert p.token_stats.rendered_context_tokens <= p.token_stats.usable_tokens


def test_research_uses_labelled_mock(sample_service, sample_repo, monkeypatch):
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    p = sample_service.build_context(
        sample_repo.repository_id, BuildOptions(task=JWT_TASK, include_research=True)
    )
    assert p.research_findings
    assert all("mock" in f.provider_status for f in p.research_findings)
    assert any("MOCK" in w for w in p.warnings)


def test_required_paths_validation(sample_service, sample_repo):
    with pytest.raises(PathSecurityError):
        sample_service.build_context(
            sample_repo.repository_id,
            BuildOptions(task=JWT_TASK, required_paths=["../../etc/passwd"]),
        )
    p = sample_service.build_context(
        sample_repo.repository_id,
        BuildOptions(
            task=JWT_TASK, token_budget=4000, required_paths=["shopapi/utils/formatting.py"]
        ),
    )
    assert any(i.path == "shopapi/utils/formatting.py" and i.required for i in p.items)


def test_unknown_repository(sample_service):
    with pytest.raises(RepositoryNotFoundError):
        sample_service.build_context("nope", BuildOptions(task="anything"))


def test_empty_and_malformed_repositories(make_repo, tmp_service):
    empty = make_repo({}, name="empty")
    empty.mkdir(parents=True, exist_ok=True)
    repo = tmp_service.index_repository(empty)
    p = tmp_service.build_context(repo.repository_id, BuildOptions(task="add login"))
    assert p.items == [] and any("no indexable files" in w.lower() for w in p.warnings)

    bad = make_repo(
        {"broken.py": "def oops(:\n", "good.py": "def login():\n    pass\n"}, name="bad"
    )
    repo = tmp_service.index_repository(bad)
    assert any("broken.py" in w and "SyntaxError" in w for w in repo.report.parse_warnings)
    p = tmp_service.build_context(repo.repository_id, BuildOptions(task="fix login"))
    assert "good.py" in {i.path for i in p.items}
