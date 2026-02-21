"""Tests for topological sort (Kahn's algorithm)."""
from __future__ import annotations

import pytest

from chronoguard_lite.graph.adjacency import Graph
from chronoguard_lite.graph.topological import CyclicDependencyError, topological_sort


class TestTopologicalSort:
    def test_empty_graph(self, empty_graph: Graph[str]) -> None:
        assert topological_sort(empty_graph) == []

    def test_single_node(self) -> None:
        g: Graph[str] = Graph()
        g.add_node("A")
        assert topological_sort(g) == ["A"]

    def test_linear(self, linear_graph: Graph[str]) -> None:
        order = topological_sort(linear_graph)
        assert order == ["A", "B", "C", "D"]

    def test_diamond(self, diamond_graph: Graph[str]) -> None:
        order = topological_sort(diamond_graph)
        # A must come first, D must come last, B and C in between
        assert order[0] == "A"
        assert order[-1] == "D"
        assert set(order[1:3]) == {"B", "C"}

    def test_wide_dag(self, wide_dag: Graph[str]) -> None:
        order = topological_sort(wide_dag)
        assert order[0] == "root"
        # every L1 node appears before its L2 children
        pos = {node: i for i, node in enumerate(order)}
        for i in range(10):
            child = f"L1_{i}"
            for j in range(2):
                grandchild = f"L2_{i}_{j}"
                assert pos[child] < pos[grandchild], (
                    f"{child} should come before {grandchild}"
                )

    def test_disconnected_components(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        g.add_edge("C", "D")
        order = topological_sort(g)
        assert len(order) == 4
        pos = {n: i for i, n in enumerate(order)}
        assert pos["A"] < pos["B"]
        assert pos["C"] < pos["D"]

    def test_cycle_raises(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        g.add_edge("B", "C")
        g.add_edge("C", "A")
        with pytest.raises(CyclicDependencyError) as exc_info:
            topological_sort(g)
        assert len(exc_info.value.remaining_nodes) == 3

    def test_self_loop_raises(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("A", "A")
        with pytest.raises(CyclicDependencyError):
            topological_sort(g)

    def test_ordering_respects_all_edges(self) -> None:
        """Every edge (u, v) must have u before v in the output."""
        g: Graph[str] = Graph()
        edges = [
            ("A", "C"), ("A", "D"), ("B", "D"), ("B", "E"),
            ("C", "F"), ("D", "F"), ("E", "F"),
        ]
        for s, d in edges:
            g.add_edge(s, d)
        order = topological_sort(g)
        pos = {n: i for i, n in enumerate(order)}
        for s, d in edges:
            assert pos[s] < pos[d], f"Edge {s}->{d} violated"

    def test_completeness(self, wide_dag: Graph[str]) -> None:
        """Output must contain every node exactly once."""
        order = topological_sort(wide_dag)
        assert len(order) == wide_dag.node_count
        assert len(set(order)) == len(order)
