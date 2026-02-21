"""Tests for critical path analysis on weighted DAGs."""
from __future__ import annotations

import pytest

from chronoguard_lite.graph.adjacency import Graph
from chronoguard_lite.graph.critical_path import CriticalPath, critical_path
from chronoguard_lite.graph.topological import CyclicDependencyError


class TestCriticalPath:
    def test_single_node(self) -> None:
        g: Graph[str] = Graph()
        g.add_node("A")
        result = critical_path(g, {"A": 5.0})
        assert result.path == ["A"]
        assert result.total_weight == 5.0
        assert result.bottleneck == "A"

    def test_linear_chain(self, linear_graph: Graph[str]) -> None:
        weights = {"A": 1.0, "B": 3.0, "C": 2.0, "D": 4.0}
        result = critical_path(linear_graph, weights)
        assert result.path == ["A", "B", "C", "D"]
        assert result.total_weight == pytest.approx(10.0)
        assert result.bottleneck == "D"
        assert result.bottleneck_weight == 4.0

    def test_diamond_picks_heavier_branch(self, diamond_graph: Graph[str]) -> None:
        # A->B->D and A->C->D.  Make B branch heavier.
        weights = {"A": 1.0, "B": 10.0, "C": 2.0, "D": 1.0}
        result = critical_path(diamond_graph, weights)
        assert result.path == ["A", "B", "D"]
        assert result.total_weight == pytest.approx(12.0)
        assert result.bottleneck == "B"

    def test_diamond_picks_lighter_when_reversed(
        self, diamond_graph: Graph[str]
    ) -> None:
        weights = {"A": 1.0, "B": 2.0, "C": 10.0, "D": 1.0}
        result = critical_path(diamond_graph, weights)
        assert result.path == ["A", "C", "D"]
        assert result.total_weight == pytest.approx(12.0)

    def test_wide_dag_bottleneck(self, wide_dag: Graph[str]) -> None:
        weights: dict[str, float] = {"root": 0.5}
        for i in range(10):
            weights[f"L1_{i}"] = 1.0
            for j in range(2):
                weights[f"L2_{i}_{j}"] = 0.1
        # all branches equal, any path is valid
        result = critical_path(wide_dag, weights)
        assert result.total_weight == pytest.approx(1.6)
        assert len(result.path) == 3  # root -> L1_x -> L2_x_y

    def test_deep_chain(self) -> None:
        """10-deep chain with one heavy node."""
        g: Graph[int] = Graph()
        for i in range(9):
            g.add_edge(i, i + 1)
        weights = {i: 1.0 for i in range(10)}
        weights[5] = 20.0  # bottleneck
        result = critical_path(g, weights)
        assert result.path == list(range(10))
        assert result.total_weight == pytest.approx(29.0)
        assert result.bottleneck == 5
        assert result.bottleneck_weight == 20.0

    def test_missing_weight_treated_as_zero(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        result = critical_path(g, {"B": 3.0})
        # A has weight 0, B has weight 3
        assert result.total_weight == pytest.approx(3.0)

    def test_empty_graph_raises(self) -> None:
        g: Graph[str] = Graph()
        with pytest.raises(ValueError, match="empty graph"):
            critical_path(g, {})

    def test_cyclic_graph_raises(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        g.add_edge("B", "A")
        with pytest.raises(CyclicDependencyError):
            critical_path(g, {"A": 1.0, "B": 1.0})

    def test_parallel_paths_finds_longest(self) -> None:
        """
        S -> A -> B -> E  (cost: 1+10+1+1 = 13)
        S -> C -> D -> E  (cost: 1+2+2+1 = 6)
        """
        g: Graph[str] = Graph()
        g.add_edge("S", "A")
        g.add_edge("A", "B")
        g.add_edge("B", "E")
        g.add_edge("S", "C")
        g.add_edge("C", "D")
        g.add_edge("D", "E")
        weights = {"S": 1.0, "A": 10.0, "B": 1.0, "C": 2.0, "D": 2.0, "E": 1.0}
        result = critical_path(g, weights)
        assert result.path == ["S", "A", "B", "E"]
        assert result.total_weight == pytest.approx(13.0)
        assert result.bottleneck == "A"
