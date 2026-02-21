"""Topological sort via Kahn's algorithm (BFS with in-degree tracking).

Kahn's algorithm is a good fit for policy evaluation ordering because
it naturally produces a breadth-first ordering: policies with no
dependencies come first, then policies whose only dependencies are
those zero-dependency policies, and so on.  The alternative (DFS
post-order reversal) gives a valid topological order too, but Kahn's
makes the "layers" explicit, which is useful for understanding
evaluation depth.

The algorithm:
  1.  Compute in-degree for every node.
  2.  Seed a queue with all nodes whose in-degree is 0.
  3.  Pop a node, append it to the result, decrement in-degree of its
      successors.  Any successor whose in-degree drops to 0 enters the
      queue.
  4.  If the result contains all nodes, the graph is a DAG.
      Otherwise there is at least one cycle.
"""
from __future__ import annotations

from collections import deque
from typing import Hashable, TypeVar

from chronoguard_lite.graph.adjacency import Graph

T = TypeVar("T", bound=Hashable)


class CyclicDependencyError(Exception):
    """Raised when topological sort encounters a cycle."""

    def __init__(self, remaining_nodes: list) -> None:
        self.remaining_nodes = remaining_nodes
        super().__init__(
            f"Cycle detected: {len(remaining_nodes)} node(s) involved in "
            f"circular dependencies"
        )


def topological_sort(graph: Graph[T]) -> list[T]:
    """Return nodes in dependency order (prerequisites first).

    Raises CyclicDependencyError if the graph contains a cycle.
    """
    in_deg: dict[T, int] = {}
    for node in graph.nodes():
        in_deg[node] = graph.in_degree(node)

    q: deque[T] = deque()
    for node, deg in in_deg.items():
        if deg == 0:
            q.append(node)

    result: list[T] = []
    while q:
        node = q.popleft()
        result.append(node)
        for succ in graph.successors(node):
            in_deg[succ] -= 1
            if in_deg[succ] == 0:
                q.append(succ)

    if len(result) != graph.node_count:
        remaining = [n for n in graph.nodes() if n not in set(result)]
        raise CyclicDependencyError(remaining)

    return result
