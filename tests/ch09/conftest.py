"""Shared fixtures for Chapter 9 graph tests."""
from __future__ import annotations

import uuid
from datetime import datetime, time, timezone

import pytest

from chronoguard_lite.domain.policy import (
    Policy,
    PolicyRule,
    PolicyStatus,
    RuleAction,
    TimeWindow,
)
from chronoguard_lite.graph.adjacency import Graph

SEED = 42


@pytest.fixture
def empty_graph() -> Graph[str]:
    return Graph()


@pytest.fixture
def linear_graph() -> Graph[str]:
    """A -> B -> C -> D"""
    g: Graph[str] = Graph()
    for src, dst in [("A", "B"), ("B", "C"), ("C", "D")]:
        g.add_edge(src, dst)
    return g


@pytest.fixture
def diamond_graph() -> Graph[str]:
    """
    A -> B -> D
    A -> C -> D
    """
    g: Graph[str] = Graph()
    for src, dst in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]:
        g.add_edge(src, dst)
    return g


@pytest.fixture
def wide_dag() -> Graph[str]:
    """Root with 10 children, each with 2 grandchildren (all leaves)."""
    g: Graph[str] = Graph()
    for i in range(10):
        child = f"L1_{i}"
        g.add_edge("root", child)
        for j in range(2):
            g.add_edge(child, f"L2_{i}_{j}")
    return g


def make_policy(
    name: str,
    domain_pattern: str = "*.example.com",
    action: RuleAction = RuleAction.ALLOW,
    priority: int = 100,
) -> Policy:
    """Create a test policy with a single rule."""
    p = Policy(
        policy_id=uuid.uuid4(),
        name=name,
        description=f"Test policy: {name}",
        rules=[],
        status=PolicyStatus.ACTIVE,
        priority=priority,
    )
    p.rules.append(PolicyRule(
        rule_id=uuid.uuid4(),
        domain_pattern=domain_pattern,
        action=action,
        priority=priority,
    ))
    return p


REQUEST_TIME = datetime(2025, 6, 15, 14, 30, tzinfo=timezone.utc)
