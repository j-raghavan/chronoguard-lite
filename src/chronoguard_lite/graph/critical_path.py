"""Critical path analysis on a weighted DAG.

The critical path is the longest path through the graph when edges are
weighted by the evaluation cost of the source node.  In a policy DAG
this tells you which chain of policies takes the most total time to
evaluate, and which single policy in that chain is the bottleneck.

Algorithm:
  1.  Topologically sort the DAG.
  2.  Walk nodes in topological order.  For each node v, for each
      successor w, relax: if dist[v] + weight[v] > dist[w], update
      dist[w] and record v as the predecessor of w on the longest path.
  3.  The node with the largest dist + weight value is the endpoint.
  4.  Walk predecessors backward to reconstruct the full path.

This is the standard DAG longest-path algorithm.  It runs in O(V + E),
which is much better than negating weights and running Dijkstra (which
would also work but adds a log factor from the heap).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar

from chronoguard_lite.graph.adjacency import Graph
from chronoguard_lite.graph.topological import topological_sort

T = TypeVar("T", bound=Hashable)


@dataclass(slots=True)
class CriticalPath(Generic[T]):
    """Result of critical path analysis."""
    path: list[T]
    total_weight: float
    bottleneck: T          # the single node with the largest weight on the path
    bottleneck_weight: float


def critical_path(graph: Graph[T], weights: dict[T, float]) -> CriticalPath[T]:
    """Find the longest weighted path through *graph*.

    *weights* maps each node to its cost (e.g. policy evaluation time
    in milliseconds).  Nodes not in *weights* are treated as zero cost.

    Raises CyclicDependencyError (via topological_sort) if the graph
    has a cycle.
    """
    order = topological_sort(graph)

    dist: dict[T, float] = {n: 0.0 for n in order}
    pred: dict[T, T | None] = {n: None for n in order}

    for node in order:
        w = weights.get(node, 0.0)
        for succ in graph.successors(node):
            new_dist = dist[node] + w
            if new_dist > dist[succ]:
                dist[succ] = new_dist
                pred[succ] = node

    # find the endpoint: node with max dist[v] + weight[v]
    best_node: T | None = None
    best_total = -1.0
    for node in order:
        total = dist[node] + weights.get(node, 0.0)
        if total > best_total:
            best_total = total
            best_node = node

    if best_node is None:
        # empty graph
        raise ValueError("Cannot compute critical path of an empty graph")

    # reconstruct path
    path: list[T] = [best_node]
    cur = best_node
    while pred[cur] is not None:
        cur = pred[cur]  # type: ignore[assignment]
        path.append(cur)
    path.reverse()

    # find the bottleneck (heaviest node on the path)
    bn = max(path, key=lambda n: weights.get(n, 0.0))

    return CriticalPath(
        path=path,
        total_weight=best_total,
        bottleneck=bn,
        bottleneck_weight=weights.get(bn, 0.0),
    )
