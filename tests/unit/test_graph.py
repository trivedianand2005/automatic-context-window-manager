import json

import networkx as nx

from app.core.models import RepoFile
from app.graph.dependency_graph import (
    build_dependency_graph,
    file_node,
    serialize_graph,
    sym_node,
    to_dot,
)
from app.graph.graph_expansion import expand
from app.ingestion.language_detector import detect_file_type, detect_language
from app.parsing.import_resolver import resolve_all
from app.parsing.python_parser import parse_python


def build(files: dict[str, str], explicit=None):
    repo_files = []
    for path, content in files.items():
        lang = detect_language(path)
        repo_files.append(
            RepoFile(
                path=path,
                language=lang,
                file_type=detect_file_type(path, lang),
                size_bytes=len(content),
                sha256="x",
                tokens=1,
                content=content,
                line_count=content.count("\n"),
            )
        )
    modules = [parse_python(f.path, f.content) for f in repo_files if f.language == "python"]
    return build_dependency_graph(repo_files, modules, resolve_all(modules), explicit)


FILES = {
    "app/__init__.py": "",
    "app/routes.py": "from app.service import Service\n\n\ndef route():\n    return Service()\n",
    "app/service.py": "from app.settings import CONFIG\n\n\nclass Service:\n"
    "    def run(self):\n        pass\n",
    "app/settings.py": "CONFIG = {'path': 'settings.yaml'}\n",
    "settings.yaml": "a: 1\n",
    "tests/test_service.py": "from app.service import Service\n",
    "tests/test_routes.py": "def test_x():\n    pass\n",
}


def test_graph_edges_and_relations():
    g = build(FILES)
    edge = g.get_edge_data(file_node("app/routes.py"), file_node("app/service.py"))
    assert edge["relation"] == "imports" and edge["confidence"] == "high"
    assert g.has_edge(file_node("app/service.py"), sym_node("app/service.py::Service"))
    assert g.has_edge(sym_node("app/service.py::Service"), sym_node("app/service.py::Service.run"))
    test_edge = g.get_edge_data(file_node("tests/test_service.py"), file_node("app/service.py"))
    assert "tests" in test_edge["relations"]
    naming = g.get_edge_data(file_node("tests/test_routes.py"), file_node("app/routes.py"))
    assert naming["relation"] == "tests" and naming["confidence"] == "medium"
    ref = g.get_edge_data(file_node("app/settings.py"), file_node("settings.yaml"))
    assert ref["relation"] == "references"


def test_explicit_dependencies():
    g = build(FILES, explicit=[("app/routes.py", "settings.yaml")])
    assert (
        g.get_edge_data(file_node("app/routes.py"), file_node("settings.yaml"))["relation"]
        == "configured"
    )


def test_expansion_follows_route_to_service_to_config():
    g = build(FILES)
    hits = expand(g, {"app/routes.py": 1.0}, max_depth=2)
    assert hits["app/service.py"].depth == 1
    assert hits["app/settings.py"].via == ["app/routes.py", "app/service.py", "app/settings.py"]
    assert hits["app/service.py"].score > hits["app/settings.py"].score
    assert "settings.yaml" not in hits  # depth 3
    deeper = expand(g, {"app/routes.py": 1.0}, max_depth=3)
    assert "settings.yaml" in deeper


def test_expansion_depth_zero_and_scores_bounded():
    g = build(FILES)
    assert expand(g, {"app/routes.py": 1.0}, max_depth=0) == {}
    for hit in expand(g, {"app/routes.py": 1.0, "app/service.py": 0.8}, max_depth=3).values():
        assert 0 < hit.score <= 1


def test_expansion_is_cycle_safe():
    g = nx.DiGraph()
    for p in "abc":
        g.add_node(file_node(p), kind="file", path=p, file_type="source")
    for u, v in [("a", "b"), ("b", "c"), ("c", "a")]:
        g.add_edge(file_node(u), file_node(v), relation="imports", confidence="high")
    hits = expand(g, {"a": 1.0}, max_depth=5)
    assert set(hits) == {"b", "c"}


def test_serialization_and_dot():
    g = build(FILES)
    data = serialize_graph(g)
    json.dumps(data)
    assert all(n["kind"] == "file" for n in data["nodes"])
    dot = to_dot(g, highlight={"app/service.py"})
    assert dot.startswith("digraph") and '"app/service.py"' in dot and "imports" in dot
