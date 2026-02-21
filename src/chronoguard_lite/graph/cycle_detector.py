"""Cycle detection in directed graphs using DFS three-color marking.

The three colors:
  WHITE  -- node not yet visited
  GRAY   -- node is on the current DFS path (ancestors of current node)
  BLACK  -- node fully explored (all descendants visited)

A back edge (an edge to a GRAY node) means the graph has a cycle.
When we find one, we reconstruct the cycle path from the recursion
stack so we can report exactly which policies form the loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar

from chronoguard_lite.graph.adjacency import Graph

T = TypeVar("T", bound=Hashable)

WHITE, GRAY, BLACK = 0, 1, 2


@dataclass(slots=True)
class CycleResult(Generic[T]):
    """Result of cycle detection."""
    has_cycle: bool
    cycle_path: list[T] | None = None


def detect_cycle(graph: Graph[T]) -> CycleResult[T]:
    """Detect whether *graph* contains a directed cycle.

    Returns a CycleResult with has_cycle=True and the cycle path if one
    exists.  The cycle path is a list [v0, v1, ..., vk, v0] where each
    consecutive pair is a directed edge.
    """
    color: dict[T, int] = {n: WHITE for n in graph.nodes()}
    parent: dict[T, T | None] = {n: None for n in graph.nodes()}

    def _dfs(node: T) -> list[T] | None:
        color[node] = GRAY
        for succ in graph.successors(node):
            if color[succ] == GRAY:
                # found a back edge -> reconstruct cycle
                path = [succ, node]
                cur = node
                while cur != succ:
                    cur = parent[cur]  # type: ignore[assignment]
                    if cur is None:
                        break
                    path.append(cur)
                path.reverse()
                return path
            if color[succ] == WHITE:
                parent[succ] = node
                cycle = _dfs(succ)
                if cycle is not None:
                    return cycle
        color[node] = BLACK
        return None

    for node in graph.nodes():
        if color[node] == WHITE:
            cycle = _dfs(node)
            if cycle is not None:
                return CycleResult(has_cycle=True, cycle_path=cycle)

    return CycleResult(has_cycle=False, cycle_path=None)
