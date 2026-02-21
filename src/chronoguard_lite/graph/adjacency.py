"""Generic directed graph using adjacency lists.

The graph stores nodes of any hashable type T and directed edges
between them.  Internally it is a dict[T, list[T]] where keys are
source nodes and values are lists of successor nodes.  A separate
reverse map tracks predecessors so in-degree queries are O(1) instead
of requiring a full scan.

ChronoGuard Lite uses this as the backbone for the policy dependency
DAG: nodes are PolicyId values, edges mean "depends on".
"""
from __future__ import annotations

from typing import Generic, Hashable, Iterator, TypeVar

T = TypeVar("T", bound=Hashable)


class Graph(Generic[T]):
    """Directed graph backed by adjacency lists.

    Maintains both forward (successors) and reverse (predecessors)
    adjacency maps so that in_degree lookups are constant time.
    """

    __slots__ = ("_fwd", "_rev")

    def __init__(self) -> None:
        self._fwd: dict[T, list[T]] = {}
        self._rev: dict[T, list[T]] = {}

    # ---- mutation --------------------------------------------------------

    def add_node(self, node: T) -> None:
        """Add *node* if it does not already exist."""
        if node not in self._fwd:
            self._fwd[node] = []
            self._rev[node] = []

    def add_edge(self, src: T, dst: T) -> None:
        """Add a directed edge src -> dst.

        Creates both nodes if they are missing.  Duplicate edges are
        silently allowed (the graph is not a multigraph by intent, but
        we don't pay the cost of checking on every insert -- callers
        that care should use has_edge first).
        """
        self.add_node(src)
        self.add_node(dst)
        self._fwd[src].append(dst)
        self._rev[dst].append(src)

    def remove_edge(self, src: T, dst: T) -> None:
        """Remove one occurrence of edge src -> dst.

        Raises ValueError if the edge does not exist.
        """
        try:
            self._fwd[src].remove(dst)
            self._rev[dst].remove(src)
        except (KeyError, ValueError):
            raise ValueError(f"Edge {src!r} -> {dst!r} not found") from None

    def remove_node(self, node: T) -> None:
        """Remove *node* and all edges touching it."""
        if node not in self._fwd:
            raise ValueError(f"Node {node!r} not found")
        # drop forward edges from this node
        for dst in self._fwd[node]:
            self._rev[dst].remove(node)
        # drop reverse edges into this node
        for src in self._rev[node]:
            self._fwd[src].remove(node)
        del self._fwd[node]
        del self._rev[node]

    # ---- queries ---------------------------------------------------------

    def has_node(self, node: T) -> bool:
        return node in self._fwd

    def has_edge(self, src: T, dst: T) -> bool:
        return src in self._fwd and dst in self._fwd[src]

    def successors(self, node: T) -> list[T]:
        """Direct successors (neighbors along outgoing edges)."""
        return list(self._fwd.get(node, []))

    def predecessors(self, node: T) -> list[T]:
        """Direct predecessors (nodes with an edge into *node*)."""
        return list(self._rev.get(node, []))

    def in_degree(self, node: T) -> int:
        return len(self._rev.get(node, []))

    def out_degree(self, node: T) -> int:
        return len(self._fwd.get(node, []))

    def nodes(self) -> Iterator[T]:
        return iter(self._fwd)

    def edges(self) -> Iterator[tuple[T, T]]:
        for src, dsts in self._fwd.items():
            for dst in dsts:
                yield src, dst

    @property
    def node_count(self) -> int:
        return len(self._fwd)

    @property
    def edge_count(self) -> int:
        return sum(len(dsts) for dsts in self._fwd.values())

    # ---- dunder ----------------------------------------------------------

    def __contains__(self, node: T) -> bool:  # type: ignore[override]
        return self.has_node(node)

    def __len__(self) -> int:
        return self.node_count

    def __repr__(self) -> str:
        return f"Graph(nodes={self.node_count}, edges={self.edge_count})"
