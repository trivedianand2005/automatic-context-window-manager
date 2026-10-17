from app.analysis.task_analyzer import analyze_task, query_terms
from app.analysis.text_processing import split_identifier, tokenize
from app.core.config import RankingWeights, Settings
from app.ingestion.repository_scanner import scan_repository
from app.parsing.python_parser import parse_python
from app.retrieval.hybrid_ranker import rank_candidates
from app.retrieval.lexical_search import LexicalIndex
from app.retrieval.semantic_search import SemanticSearcher, semantic_dependencies_installed
from app.services.acwm_service import ACWMService
from tests.conftest import MINI_PROJECT


def test_identifier_splitting_and_tokenize():
    assert split_identifier("getCurrentUser") == ["get", "current", "user"]
    assert split_identifier("HTTPServer_config") == ["http", "server", "config"]
    assert "jwt" in tokenize("Use JWT tokens")
    assert "the" not in tokenize("the token")


def _index(make_repo, tmp_path):
    root = make_repo(MINI_PROJECT)
    scan = scan_repository(root, Settings(allowed_roots=[tmp_path]))
    modules = {
        f.path: parse_python(f.path, f.content) for f in scan.files if f.language == "python"
    }
    return scan, modules, LexicalIndex(scan.files, modules)


def test_bm25_ranks_relevant_file_first_with_explanations(make_repo, tmp_path):
    _, _, index = _index(make_repo, tmp_path)
    hits = index.search(["auth", "token"], ["verify"])
    top2 = {h.path: h for h in hits[:2]}
    assert set(top2) == {"pkg/auth.py", "tests/test_auth.py"}  # source and its test
    auth = top2["pkg/auth.py"]
    assert {"auth", "token"} <= set(auth.matched_terms)
    assert "pkg/auth.py::create_token" in auth.matched_symbols
    assert all(h.path != "pkg/unrelated.py" for h in hits)


def test_bm25_deterministic_and_empty_query(make_repo, tmp_path):
    _, _, index = _index(make_repo, tmp_path)
    first = [(h.path, h.score) for h in index.search(["token"])]
    second = [(h.path, h.score) for h in index.search(["token"])]
    assert first == second
    assert index.search([]) == []


def test_empty_index():
    assert LexicalIndex([], {}).search(["x"]) == []


def test_hybrid_scores_are_normalised_and_explained(make_repo, tmp_path, tmp_settings):
    service = ACWMService(tmp_settings)
    repo = service.index_repository(make_repo(MINI_PROJECT))
    analysis = analyze_task("Add token expiry to protected_route and add tests")
    primary, secondary = query_terms(analysis)
    hits = repo.lexical.search(primary, secondary)
    cands, expansion = rank_candidates(
        list(repo.files.values()),
        repo.modules,
        repo.graph,
        hits,
        analysis,
        primary,
        secondary,
        RankingWeights(),
    )
    for c in cands:
        assert 0 <= c.combined <= 1
        for v in c.scores.model_dump().values():
            assert 0 <= v <= 1
        assert c.reasons
    by_path = {c.path: c for c in cands}
    assert by_path["pkg/routes.py"].scores.symbol == 1.0  # exact symbol name in task
    assert "pkg/auth.py" in expansion  # reached from routes via import
    assert by_path["tests/test_auth.py"].scores.test > 0
    assert cands == sorted(cands, key=lambda c: (-c.combined, c.path))


def test_weights_change_ranking(make_repo, tmp_settings):
    service = ACWMService(tmp_settings)
    repo = service.index_repository(make_repo(MINI_PROJECT))
    analysis = analyze_task("verify token")
    primary, secondary = query_terms(analysis)
    hits = repo.lexical.search(primary, secondary)
    only_lex = RankingWeights(lexical=1, filename=0, symbol=0, dependency=0, test=0, config=0)
    only_dep = RankingWeights(lexical=0, filename=0, symbol=0, dependency=1, test=0, config=0)
    a, _ = rank_candidates(
        list(repo.files.values()),
        repo.modules,
        repo.graph,
        hits,
        analysis,
        primary,
        secondary,
        only_lex,
    )
    b, _ = rank_candidates(
        list(repo.files.values()),
        repo.modules,
        repo.graph,
        hits,
        analysis,
        primary,
        secondary,
        only_dep,
    )
    assert [c.path for c in a] != [c.path for c in b]


def test_semantic_unavailable_is_reported_not_faked():
    searcher = SemanticSearcher()
    if semantic_dependencies_installed():
        return
    assert not searcher.available
    assert "not installed" in searcher.reason
    assert searcher.score("q", {"a.py": "x"}) == {}


def test_task_analyzer_extracts_terms():
    a = analyze_task(
        "Fix `retry_with_backoff` in database.py and add pytest regression tests "
        "for SHOPAPI settings"
    )
    assert a.wants_tests
    assert "retry_with_backoff" in a.component_names
    assert "database.py" in a.component_names
    assert "settings" in a.config_terms
    assert "backoff" in a.expanded_terms
    primary, _ = query_terms(a)
    assert "db" in primary  # canonical short form of "database"
