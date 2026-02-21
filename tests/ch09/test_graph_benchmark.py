"""Benchmark tests for Chapter 9 graph algorithms.

These tests measure actual performance and record numbers for the
chapter prose.  They are not micro-benchmarks with warmup loops --
they run realistic workloads and report wall-clock times.
"""
from __future__ import annotations

import random
import time
import uuid

import pytest

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import (
    Policy,
    PolicyRule,
    PolicyStatus,
    RuleAction,
)
from chronoguard_lite.graph.adjacency import Graph
from chronoguard_lite.graph.critical_path import critical_path
from chronoguard_lite.graph.cycle_detector import detect_cycle
from chronoguard_lite.graph.policy_engine import PolicyEngine
from chronoguard_lite.graph.topological import topological_sort

from .conftest import REQUEST_TIME

SEED = 42


def _make_dag(n_nodes: int, edge_prob: float, seed: int = SEED) -> Graph[int]:
    """Build a random DAG with n_nodes and forward edges only."""
    rng = random.Random(seed)
    g: Graph[int] = Graph()
    for i in range(n_nodes):
        g.add_node(i)
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            if rng.random() < edge_prob:
                g.add_edge(i, j)
    return g


def _make_layered_dag(
    n_layers: int, width: int, seed: int = SEED
) -> Graph[str]:
    """Build a layered DAG: each node in layer i connects to 1-3
    nodes in layer i+1."""
    rng = random.Random(seed)
    g: Graph[str] = Graph()
    for layer in range(n_layers):
        for w in range(width):
            node = f"L{layer}_{w}"
            g.add_node(node)
            if layer > 0:
                # connect from 1-3 nodes in previous layer
                n_parents = min(rng.randint(1, 3), width)
                parents = rng.sample(range(width), n_parents)
                for p in parents:
                    g.add_edge(f"L{layer-1}_{p}", node)
    return g


def _make_policy_engine(
    n_policies: int,
    n_layers: int,
    deny_rate: float = 0.3,
    seed: int = SEED,
) -> PolicyEngine:
    """Build a layered policy DAG for benchmarking.

    deny_rate controls what fraction of policies have DENY rules for
    the test domain.  Higher deny_rate means more short-circuiting.
    """
    rng = random.Random(seed)
    engine = PolicyEngine()
    policies_by_layer: list[list[Policy]] = []
    policies_per_layer = max(1, n_policies // n_layers)

    for layer in range(n_layers):
        layer_policies = []
        for i in range(policies_per_layer):
            action = RuleAction.DENY if rng.random() < deny_rate else RuleAction.ALLOW
            p = Policy(
                policy_id=uuid.uuid4(),
                name=f"policy_L{layer}_{i}",
                description=f"Layer {layer} policy {i}",
                rules=[PolicyRule(
                    rule_id=uuid.uuid4(),
                    domain_pattern="*.example.com",
                    action=action,
                    priority=100,
                )],
                status=PolicyStatus.ACTIVE,
                priority=layer * 100 + i,
            )
            engine.register(p)
            layer_policies.append(p)

            # add dependency on 1-2 policies from previous layer
            if layer > 0 and policies_by_layer[layer - 1]:
                n_deps = min(rng.randint(1, 2), len(policies_by_layer[layer - 1]))
                deps = rng.sample(policies_by_layer[layer - 1], n_deps)
                for dep in deps:
                    engine.add_dependency(p.policy_id, depends_on=dep.policy_id)

        policies_by_layer.append(layer_policies)

    engine.build()
    return engine


class TestTopologicalSortPerformance:
    def test_toposort_1000_nodes(self) -> None:
        g = _make_dag(1000, 0.01)
        t0 = time.perf_counter()
        for _ in range(100):
            topological_sort(g)
        elapsed = (time.perf_counter() - t0) / 100 * 1000
        print(f"\nToposort 1000 nodes: {elapsed:.3f} ms/sort")
        print(f"  nodes={g.node_count}, edges={g.edge_count}")
        assert elapsed < 50  # sanity: should be well under 50ms

    def test_toposort_5000_nodes(self) -> None:
        g = _make_dag(5000, 0.002)
        t0 = time.perf_counter()
        for _ in range(20):
            topological_sort(g)
        elapsed = (time.perf_counter() - t0) / 20 * 1000
        print(f"\nToposort 5000 nodes: {elapsed:.3f} ms/sort")
        print(f"  nodes={g.node_count}, edges={g.edge_count}")
        assert elapsed < 200


class TestCycleDetectionPerformance:
    def test_cycle_detect_1000_dag(self) -> None:
        g = _make_dag(1000, 0.01)
        t0 = time.perf_counter()
        for _ in range(100):
            detect_cycle(g)
        elapsed = (time.perf_counter() - t0) / 100 * 1000
        print(f"\nCycle detection 1000-node DAG: {elapsed:.3f} ms")
        assert elapsed < 50

    def test_cycle_detect_1000_with_cycle(self) -> None:
        g = _make_dag(1000, 0.01)
        # add a back edge to create cycle
        g.add_edge(999, 0)
        t0 = time.perf_counter()
        for _ in range(100):
            result = detect_cycle(g)
        elapsed = (time.perf_counter() - t0) / 100 * 1000
        print(f"\nCycle detection 1000-node graph with cycle: {elapsed:.3f} ms")
        assert result.has_cycle
        assert elapsed < 50


class TestCriticalPathPerformance:
    def test_critical_path_layered(self) -> None:
        g = _make_layered_dag(10, 50)
        rng = random.Random(SEED)
        weights = {n: rng.uniform(0.1, 5.0) for n in g.nodes()}
        t0 = time.perf_counter()
        for _ in range(100):
            result = critical_path(g, weights)
        elapsed = (time.perf_counter() - t0) / 100 * 1000
        print(f"\nCritical path (10 layers x 50 wide): {elapsed:.3f} ms")
        print(f"  nodes={g.node_count}, edges={g.edge_count}")
        print(f"  path length={len(result.path)}, total={result.total_weight:.1f}ms")
        print(f"  bottleneck={result.bottleneck} ({result.bottleneck_weight:.1f}ms)")
        assert elapsed < 100


class TestPolicyEnginePerformance:
    def test_dag_vs_flat_50_policies_high_deny(self) -> None:
        """50 policies, 10 layers, 30% deny rate."""
        engine = _make_policy_engine(50, 10, deny_rate=0.3)
        domain = "api.example.com"

        # DAG evaluation (with short-circuit)
        n_iters = 500
        t0 = time.perf_counter()
        for _ in range(n_iters):
            dag_report = engine.evaluate(domain, REQUEST_TIME)
        dag_ms = (time.perf_counter() - t0) / n_iters * 1000

        # Flat evaluation (no short-circuit)
        t0 = time.perf_counter()
        for _ in range(n_iters):
            flat_report = engine.evaluate_flat(domain, REQUEST_TIME)
        flat_ms = (time.perf_counter() - t0) / n_iters * 1000

        speedup = flat_ms / dag_ms if dag_ms > 0 else float("inf")
        print(f"\n50-policy DAG (30% deny):")
        print(f"  DAG eval:  {dag_ms:.4f} ms/request")
        print(f"  Flat eval: {flat_ms:.4f} ms/request")
        print(f"  Speedup:   {speedup:.1f}x")
        print(f"  Policies evaluated (DAG): {dag_report.policies_evaluated}")
        print(f"  Policies skipped (DAG):   {dag_report.policies_skipped}")
        print(f"  Policies evaluated (flat): {flat_report.policies_evaluated}")
        assert dag_report.policies_skipped > 0
        assert speedup > 1.0

    def test_dag_vs_flat_50_policies_low_deny(self) -> None:
        """50 policies, 10 layers, 5% deny rate (minimal short-circuit)."""
        engine = _make_policy_engine(50, 10, deny_rate=0.05, seed=99)
        domain = "api.example.com"

        n_iters = 500
        t0 = time.perf_counter()
        for _ in range(n_iters):
            dag_report = engine.evaluate(domain, REQUEST_TIME)
        dag_ms = (time.perf_counter() - t0) / n_iters * 1000

        t0 = time.perf_counter()
        for _ in range(n_iters):
            flat_report = engine.evaluate_flat(domain, REQUEST_TIME)
        flat_ms = (time.perf_counter() - t0) / n_iters * 1000

        speedup = flat_ms / dag_ms if dag_ms > 0 else float("inf")
        print(f"\n50-policy DAG (5% deny):")
        print(f"  DAG eval:  {dag_ms:.4f} ms/request")
        print(f"  Flat eval: {flat_ms:.4f} ms/request")
        print(f"  Speedup:   {speedup:.1f}x")
        print(f"  Policies evaluated (DAG): {dag_report.policies_evaluated}")
        print(f"  Policies skipped (DAG):   {dag_report.policies_skipped}")

    def test_dag_vs_flat_200_policies(self) -> None:
        """200 policies, 20 layers, 30% deny rate."""
        engine = _make_policy_engine(200, 20, deny_rate=0.3)
        domain = "api.example.com"

        n_iters = 200
        t0 = time.perf_counter()
        for _ in range(n_iters):
            dag_report = engine.evaluate(domain, REQUEST_TIME)
        dag_ms = (time.perf_counter() - t0) / n_iters * 1000

        t0 = time.perf_counter()
        for _ in range(n_iters):
            flat_report = engine.evaluate_flat(domain, REQUEST_TIME)
        flat_ms = (time.perf_counter() - t0) / n_iters * 1000

        speedup = flat_ms / dag_ms if dag_ms > 0 else float("inf")
        print(f"\n200-policy DAG (30% deny):")
        print(f"  DAG eval:  {dag_ms:.4f} ms/request")
        print(f"  Flat eval: {flat_ms:.4f} ms/request")
        print(f"  Speedup:   {speedup:.1f}x")
        print(f"  Policies evaluated (DAG): {dag_report.policies_evaluated}")
        print(f"  Policies skipped (DAG):   {dag_report.policies_skipped}")
        assert speedup > 1.0

    def test_toposort_overhead(self) -> None:
        """Measure overhead of topological sort relative to total eval."""
        engine = _make_policy_engine(50, 10, deny_rate=0.0)
        domain = "api.example.com"

        # time just the sort
        n_iters = 1000
        t0 = time.perf_counter()
        for _ in range(n_iters):
            topological_sort(engine.graph)
        sort_ms = (time.perf_counter() - t0) / n_iters * 1000

        # time full eval
        t0 = time.perf_counter()
        for _ in range(n_iters):
            engine.evaluate(domain, REQUEST_TIME)
        eval_ms = (time.perf_counter() - t0) / n_iters * 1000

        pct = (sort_ms / eval_ms * 100) if eval_ms > 0 else 0
        print(f"\nToposort overhead (50 policies, no deny):")
        print(f"  Sort only: {sort_ms:.4f} ms")
        print(f"  Full eval: {eval_ms:.4f} ms")
        print(f"  Sort is {pct:.1f}% of total eval time")
