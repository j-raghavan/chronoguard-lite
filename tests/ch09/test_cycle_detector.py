"""Tests for DFS-based cycle detection."""
from __future__ import annotations

import random

import pytest

from chronoguard_lite.graph.adjacency import Graph
from chronoguard_lite.graph.cycle_detector import CycleResult, detect_cycle


class TestCycleDetector:
    def test_no_cycle_empty(self, empty_graph: Graph[str]) -> None:
        result = detect_cycle(empty_graph)
        assert not result.has_cycle
        assert result.cycle_path is None

    def test_no_cycle_linear(self, linear_graph: Graph[str]) -> None:
        result = detect_cycle(linear_graph)
        assert not result.has_cycle

    def test_no_cycle_diamond(self, diamond_graph: Graph[str]) -> None:
        result = detect_cycle(diamond_graph)
        assert not result.has_cycle

    def test_simple_cycle(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        g.add_edge("B", "A")
        result = detect_cycle(g)
        assert result.has_cycle
        assert result.cycle_path is not None
        assert len(result.cycle_path) >= 2

    def test_deep_cycle(self) -> None:
        """A -> B -> C -> D -> B (cycle of length 3)."""
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        g.add_edge("B", "C")
        g.add_edge("C", "D")
        g.add_edge("D", "B")
        result = detect_cycle(g)
        assert result.has_cycle
        path = result.cycle_path
        assert path is not None
        # the cycle should include B, C, D
        cycle_set = set(path)
        assert {"B", "C", "D"}.issubset(cycle_set)

    def test_self_loop(self) -> None:
        g: Graph[str] = Graph()
        g.add_edge("X", "X")
        result = detect_cycle(g)
        assert result.has_cycle

    def test_cycle_path_is_valid(self) -> None:
        """The reported cycle path must follow real edges."""
        g: Graph[str] = Graph()
        g.add_edge("A", "B")
        g.add_edge("B", "C")
        g.add_edge("C", "A")
        result = detect_cycle(g)
        assert result.has_cycle
        path = result.cycle_path
        assert path is not None
        # verify each consecutive pair is an edge
        for i in range(len(path) - 1):
            assert g.has_edge(path[i], path[i + 1]), (
                f"Edge {path[i]}->{path[i+1]} not in graph"
            )

    def test_no_false_positives_random_dags(self) -> None:
        """Generate 50 random DAGs, assert no false positives."""
        rng = random.Random(42)
        for _ in range(50):
            n = rng.randint(2, 30)
            nodes = list(range(n))
            g: Graph[int] = Graph()
            for node in nodes:
                g.add_node(node)
            # add random forward edges (i -> j where i < j) to guarantee DAG
            for i in range(n):
                for j in range(i + 1, n):
                    if rng.random() < 0.3:
                        g.add_edge(i, j)
            result = detect_cycle(g)
            assert not result.has_cycle, f"False positive on DAG with {n} nodes"

    def test_no_false_negatives_random_cycles(self) -> None:
        """Generate 50 random graphs with forced cycles, assert detection.

        The trick: we first build a chain 0->1->...->n-1 so there is
        a guaranteed forward path between every pair.  Then we add a
        back edge from a higher node to a lower node, which closes a
        cycle along the chain.  Without the chain, a random sparse DAG
        might not have a path from dst to src, so the back edge would
        not actually create a cycle.
        """
        rng = random.Random(43)
        for _ in range(50):
            n = rng.randint(3, 20)
            g: Graph[int] = Graph()
            # chain guarantees reachability
            for i in range(n - 1):
                g.add_edge(i, i + 1)
            # sprinkle extra forward edges
            for i in range(n):
                for j in range(i + 2, n):
                    if rng.random() < 0.2:
                        g.add_edge(i, j)
            # back edge along the chain creates a real cycle
            src = rng.randint(1, n - 1)
            dst = rng.randint(0, src - 1)
            g.add_edge(src, dst)
            result = detect_cycle(g)
            assert result.has_cycle, (
                f"False negative: missed cycle with back edge {src}->{dst}"
            )

    def test_disconnected_with_cycle(self) -> None:
        """Cycle in one component, DAG in another."""
        g: Graph[str] = Graph()
        g.add_edge("A", "B")  # DAG component
        g.add_edge("C", "D")
        g.add_edge("D", "C")  # cycle component
        result = detect_cycle(g)
        assert result.has_cycle
