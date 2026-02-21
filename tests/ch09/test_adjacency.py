"""Tests for Graph adjacency list implementation."""
from __future__ import annotations

import pytest

from chronoguard_lite.graph.adjacency import Graph


class TestGraphBasics:
    def test_empty_graph(self, empty_graph: Graph[str]) -> None:
        assert empty_graph.node_count == 0
        assert empty_graph.edge_count == 0
        assert list(empty_graph.nodes()) == []
        assert list(empty_graph.edges()) == []

    def test_add_node(self, empty_graph: Graph[str]) -> None:
        empty_graph.add_node("A")
        assert "A" in empty_graph
        assert empty_graph.node_count == 1
        assert empty_graph.edge_count == 0

    def test_add_node_idempotent(self, empty_graph: Graph[str]) -> None:
        empty_graph.add_node("A")
        empty_graph.add_node("A")
        assert empty_graph.node_count == 1

    def test_add_edge_creates_nodes(self, empty_graph: Graph[str]) -> None:
        empty_graph.add_edge("X", "Y")
        assert "X" in empty_graph
        assert "Y" in empty_graph
        assert empty_graph.node_count == 2
        assert empty_graph.edge_count == 1

    def test_successors_and_predecessors(self, linear_graph: Graph[str]) -> None:
        assert linear_graph.successors("A") == ["B"]
        assert linear_graph.predecessors("B") == ["A"]
        assert linear_graph.successors("D") == []
        assert linear_graph.predecessors("A") == []

    def test_in_degree_out_degree(self, diamond_graph: Graph[str]) -> None:
        assert diamond_graph.in_degree("A") == 0
        assert diamond_graph.out_degree("A") == 2
        assert diamond_graph.in_degree("D") == 2
        assert diamond_graph.out_degree("D") == 0

    def test_remove_edge(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        g.add_edge("A", "C")
        g.remove_edge("A", "B")
        assert g.edge_count == 1
        assert g.successors("A") == ["C"]
        assert g.predecessors("B") == []

    def test_remove_edge_missing_raises(self, empty_graph: Graph[str]) -> None:
        with pytest.raises(ValueError, match="not found"):
            empty_graph.remove_edge("X", "Y")

    def test_remove_node(self, diamond_graph: Graph[str]) -> None:
        diamond_graph.remove_node("B")
        assert "B" not in diamond_graph
        assert diamond_graph.node_count == 3
        # edge A->B gone, edge B->D gone
        assert "B" not in diamond_graph.successors("A")
        assert "B" not in diamond_graph.predecessors("D")

    def test_remove_node_missing_raises(self, empty_graph: Graph[str]) -> None:
        with pytest.raises(ValueError, match="not found"):
            empty_graph.remove_node("Z")

    def test_has_edge(self, linear_graph: Graph[str]) -> None:
        assert linear_graph.has_edge("A", "B")
        assert not linear_graph.has_edge("B", "A")
        assert not linear_graph.has_edge("A", "D")

    def test_edges_iteration(self, diamond_graph: Graph[str]) -> None:
        edges = list(diamond_graph.edges())
        assert len(edges) == 4
        assert ("A", "B") in edges
        assert ("C", "D") in edges

    def test_repr(self, diamond_graph: Graph[str]) -> None:
        r = repr(diamond_graph)
        assert "nodes=4" in r
        assert "edges=4" in r

    def test_len(self, linear_graph: Graph[str]) -> None:
        assert len(linear_graph) == 4
