"""Relationship-aware relevance propagation over the file-level dependency graph.

Starting from seed files (direct task matches), relevance flows along edges:

    score(neighbour) = score(current) * relation_weight * confidence_factor * hop_decay

Traversal is breadth-first, bounded by ``max_depth``, and only revisits a node
when a strictly better score is found, so cycles terminate.
"""

from __future__ import annotations

from collections import deque

import networkx as nx
from pydantic import BaseModel

from app.graph.dependency_graph import file_node

# (relation, direction) -> weight. "forward" follows the edge, "reverse" walks it backwards.
RELATION_WEIGHTS: dict[tuple[str, str], float] = {
    ("imports", "forward"): 1.0,  # route -> service it uses
    ("imports", "reverse"): 0.45,  # module -> callers that may need updating
    ("tests", "reverse"): 0.8,  # source -> its tests
    ("tests", "forward"): 0.6,  # test -> code under test
    ("references", "forward"): 0.7,
    ("references", "reverse"): 0.3,
    ("configured", "forward"): 1.0,
    ("configured", "reverse"): 0.5,
}
CONFIDENCE_FACTOR = {"high": 1.0, "medium": 0.7, "low": 0.4}
HOP_DECAY = 0.75


class ExpansionHit(BaseModel):
    path: str
    score: float
    depth: int
    via: list[str]  # path chain from the seed to this file
    relation: str
    confidence: str


def _neighbours(graph: nx.DiGraph, node: str):
    for _, dst, data in graph.out_edges(node, data=True):
        if graph.nodes[dst].get("kind") == "file":
            yield dst, data["relation"], "forward", data["confidence"]
    for src, _, data in graph.in_edges(node, data=True):
        if graph.nodes[src].get("kind") == "file":
            yield src, data["relation"], "reverse", data["confidence"]


def expand(
    graph: nx.DiGraph,
    seeds: dict[str, float],
    max_depth: int = 2,
    test_boost: float = 1.0,
) -> dict[str, ExpansionHit]:
    """Propagate seed relevance; returns the best hit per reached (non-seed-origin) file."""
    best: dict[str, ExpansionHit] = {}
    queue: deque[tuple[str, float, int, list[str]]] = deque()
    for path, score in sorted(seeds.items()):
        if file_node(path) in graph and score > 0:
            queue.append((path, min(1.0, score), 0, [path]))

    while queue:
        path, score, depth, chain = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbour, relation, direction, confidence in sorted(
            _neighbours(graph, file_node(path))
        ):
            weight = RELATION_WEIGHTS.get((relation, direction), 0.0)
            if relation == "tests" and direction == "reverse":
                weight *= test_boost
            new_score = score * weight * CONFIDENCE_FACTOR[confidence] * HOP_DECAY
            if new_score <= 0.01:
                continue
            target = graph.nodes[neighbour]["path"]
            if target in chain:
                continue  # cycle
            current = best.get(target)
            if current is None or new_score > current.score + 1e-12:
                label = relation if direction == "forward" else f"{relation} (reverse)"
                best[target] = ExpansionHit(
                    path=target,
                    score=round(new_score, 6),
                    depth=depth + 1,
                    via=[*chain, target],
                    relation=label,
                    confidence=confidence,
                )
                queue.append((target, new_score, depth + 1, [*chain, target]))
    return best
