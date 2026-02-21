"""Tests for ConcurrentPolicyCache.

Covers: add/get/remove policies, agent assignment, concurrent access.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone

import pytest

from chronoguard_lite.concurrency.concurrent_policy_cache import ConcurrentPolicyCache
from chronoguard_lite.domain.policy import Policy, PolicyRule, PolicyStatus


def _make_policy(name: str, domain: str = "example.com") -> Policy:
    p = Policy.create(name=name, priority=10)
    p.add_rule(PolicyRule.allow(domain, priority=10))
    p.status = PolicyStatus.ACTIVE
    return p


def test_add_and_get_policy():
    cache = ConcurrentPolicyCache()
    p = _make_policy("test")
    cache.add_policy(p)
    assert cache.get_policy(p.policy_id) is p
    assert cache.policy_count() == 1


def test_remove_policy():
    cache = ConcurrentPolicyCache()
    p = _make_policy("test")
    cache.add_policy(p)
    assert cache.remove_policy(p.policy_id) is True
    assert cache.remove_policy(p.policy_id) is False
    assert cache.get_policy(p.policy_id) is None


def test_assign_policy_to_agent():
    cache = ConcurrentPolicyCache()
    p = _make_policy("test")
    cache.add_policy(p)

    agent_id = uuid.uuid4()
    cache.assign_policy_to_agent(agent_id, p.policy_id)

    policies = cache.get_policies_for_agent(agent_id)
    assert len(policies) == 1
    assert policies[0].policy_id == p.policy_id


def test_assign_idempotent():
    """Assigning the same policy twice to an agent doesn't duplicate."""
    cache = ConcurrentPolicyCache()
    p = _make_policy("test")
    cache.add_policy(p)

    agent_id = uuid.uuid4()
    cache.assign_policy_to_agent(agent_id, p.policy_id)
    cache.assign_policy_to_agent(agent_id, p.policy_id)

    policies = cache.get_policies_for_agent(agent_id)
    assert len(policies) == 1


def test_remove_policy_from_agent():
    cache = ConcurrentPolicyCache()
    p1 = _make_policy("p1")
    p2 = _make_policy("p2", domain="other.com")
    cache.add_policy(p1)
    cache.add_policy(p2)

    agent_id = uuid.uuid4()
    cache.assign_policy_to_agent(agent_id, p1.policy_id)
    cache.assign_policy_to_agent(agent_id, p2.policy_id)

    assert cache.remove_policy_from_agent(agent_id, p1.policy_id) is True
    policies = cache.get_policies_for_agent(agent_id)
    assert len(policies) == 1
    assert policies[0].policy_id == p2.policy_id


def test_get_policies_for_unknown_agent():
    cache = ConcurrentPolicyCache()
    assert cache.get_policies_for_agent(uuid.uuid4()) == []


def test_concurrent_add_and_read():
    """8 writers + 8 readers operating on the cache concurrently."""
    cache = ConcurrentPolicyCache()
    n_policies = 96  # evenly divisible by 8 writers

    # Pre-create policies
    all_policies = [_make_policy(f"p-{i}", f"svc-{i}.example.com") for i in range(n_policies)]
    agent_id = uuid.uuid4()

    def writer(start, end):
        for i in range(start, end):
            cache.add_policy(all_policies[i])
            cache.assign_policy_to_agent(agent_id, all_policies[i].policy_id)

    def reader():
        for _ in range(50):
            _ = cache.get_policies_for_agent(agent_id)
            _ = cache.policy_count()

    with ThreadPoolExecutor(max_workers=16) as pool:
        futs = []
        # 8 writers, each adding a slice of policies
        chunk = n_policies // 8
        for w in range(8):
            futs.append(pool.submit(writer, w * chunk, (w + 1) * chunk))
        # 8 readers
        for _ in range(8):
            futs.append(pool.submit(reader))
        wait(futs)
        for f in futs:
            f.result()  # raise any exceptions

    assert cache.policy_count() == n_policies
