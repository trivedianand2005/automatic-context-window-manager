"""Build a NetworkX dependency graph from parsed modules.

Nodes
  ``file:<path>``   every indexed file (attrs: kind="file", file_type, language)
  ``sym:<id>``      every Python symbol (attrs: kind="symbol", symbol_kind, name)

Edges (attr ``relation`` + ``confidence``)
  imports      file -> file      static import resolved to a repository file
  contains     file -> sym, sym -> sym (class -> method, function -> nested)
  tests        test file -> source file (via import [high] or naming convention [medium])
  references   file -> file      a string literal names another repository file [medium]
  configured   file -> file      explicitly configured dependency [high]

Static analysis cannot see dynamic imports, dependency injection by string, or
runtime call graphs, so the graph under-approximates real coupling.
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath

import networkx as nx

from app.core.models import ModuleInfo, RepoFile, ResolvedImport

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def file_node(path: str) -> str:
    return f"file:{path}"


def sym_node(symbol_id: str) -> str:
    return f"sym:{symbol_id}"


def _add_edge(graph: nx.DiGraph, src: str, dst: str, relation: str, confidence: str, **attrs):
    if src == dst:
        return
    existing = graph.get_edge_data(src, dst)
    if existing:
        # Keep the strongest evidence; remember every relation seen.
        relations = set(existing.get("relations", [existing["relation"]])) | {relation}
        existing["relations"] = sorted(relations)
        if CONFIDENCE_RANK[confidence] > CONFIDENCE_RANK[existing["confidence"]]:
            existing.update(relation=relation, confidence=confidence, **attrs)
        return
    graph.add_edge(
        src, dst, relation=relation, confidence=confidence, relations=[relation], **attrs
    )


def _string_literals(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 200
    }


def build_dependency_graph(
    files: list[RepoFile],
    modules: list[ModuleInfo],
    resolved_imports: list[ResolvedImport],
    explicit_dependencies: list[tuple[str, str]] | None = None,
) -> nx.DiGraph:
    graph = nx.DiGraph()
    by_path = {f.path: f for f in files}
    for f in files:
        graph.add_node(
            file_node(f.path),
            kind="file",
            path=f.path,
            file_type=f.file_type,
            language=f.language,
            tokens=f.tokens,
        )

    for info in modules:
        for sym in info.symbols:
            graph.add_node(
                sym_node(sym.id),
                kind="symbol",
                path=sym.path,
                name=sym.name,
                symbol_kind=sym.kind,
                qualname=sym.qualname,
            )
            parent = sym_node(f"{sym.path}::{sym.parent}") if sym.parent else file_node(sym.path)
            _add_edge(graph, parent, sym_node(sym.id), "contains", "high")

    for imp in resolved_imports:
        if imp.status == "local" and imp.target_path in by_path:
            _add_edge(
                graph,
                file_node(imp.source_path),
                file_node(imp.target_path),
                "imports",
                imp.confidence,
                line=imp.line,
                note=imp.note,
            )

    # Test -> source relationships.
    sources_by_stem: dict[str, list[str]] = {}
    for f in files:
        if f.file_type in {"source", "config"} and f.language == "python":
            sources_by_stem.setdefault(PurePosixPath(f.path).stem, []).append(f.path)
    for f in files:
        if f.file_type != "test":
            continue
        for _, target, data in list(graph.out_edges(file_node(f.path), data=True)):
            if data["relation"] == "imports" and graph.nodes[target].get("file_type") != "test":
                _add_edge(graph, file_node(f.path), target, "tests", data["confidence"])
        stem = PurePosixPath(f.path).stem
        subject = stem[5:] if stem.startswith("test_") else stem.removesuffix("_test")
        for src in sources_by_stem.get(subject, []):
            _add_edge(
                graph,
                file_node(f.path),
                file_node(src),
                "tests",
                "medium",
                note="naming convention",
            )

    # String-literal references from Python files to other repository files.
    names_to_paths: dict[str, set[str]] = {}
    for f in files:
        names_to_paths.setdefault(f.path, set()).add(f.path)
        if f.language != "python":
            names_to_paths.setdefault(PurePosixPath(f.path).name, set()).add(f.path)
    for f in files:
        if f.language != "python":
            continue
        for literal in _string_literals(f.content):
            targets = sorted(names_to_paths.get(literal.replace("\\", "/"), set()))
            if len(targets) == 1 and targets[0] != f.path:
                _add_edge(
                    graph,
                    file_node(f.path),
                    file_node(targets[0]),
                    "references",
                    "medium",
                    note=f"string literal '{literal}'",
                )

    for src, dst in explicit_dependencies or []:
        if src in by_path and dst in by_path:
            _add_edge(graph, file_node(src), file_node(dst), "configured", "high")
    return graph


def file_subgraph(graph: nx.DiGraph) -> nx.DiGraph:
    nodes = [n for n, d in graph.nodes(data=True) if d.get("kind") == "file"]
    return graph.subgraph(nodes).copy()


def serialize_graph(graph: nx.DiGraph, include_symbols: bool = False) -> dict:
    target = graph if include_symbols else file_subgraph(graph)
    return nx.node_link_data(target, edges="edges")


def to_dot(graph: nx.DiGraph, highlight: set[str] | None = None, max_nodes: int = 80) -> str:
    """Graphviz DOT for the file-level graph (rendered client-side by Streamlit)."""
    highlight = highlight or set()
    sub = file_subgraph(graph)
    nodes = sorted(sub.nodes)
    if highlight:
        keep = set()
        for path in highlight:
            node = file_node(path)
            if node in sub:
                keep.add(node)
                keep.update(sub.successors(node))
                keep.update(sub.predecessors(node))
        nodes = sorted(keep)
    nodes = nodes[:max_nodes]
    colors = {"source": "#dbeafe", "test": "#dcfce7", "config": "#fef3c7", "docs": "#f3e8ff"}
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        '  node [shape=box, style="rounded,filled", fontsize=10];',
    ]
    for n in nodes:
        data = sub.nodes[n]
        path = data["path"]
        pen = ', penwidth=2.5, color="#dc2626"' if path in highlight else ""
        lines.append(f'  "{path}" [fillcolor="{colors.get(data["file_type"], "#f1f5f9")}"{pen}];')
    style = {"high": "solid", "medium": "dashed", "low": "dotted"}
    node_set = set(nodes)
    for u, v, d in sub.edges(data=True):
        if u in node_set and v in node_set:
            lines.append(
                f'  "{sub.nodes[u]["path"]}" -> "{sub.nodes[v]["path"]}" '
                f'[label="{d["relation"]}", fontsize=8, style={style[d["confidence"]]}];'
            )
    lines.append("}")
    return "\n".join(lines)
