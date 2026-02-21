"""Tests for ColumnarAuditStore -- the struct-of-arrays optimization."""
import math
import uuid

import pytest

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.store.columnar_store import ColumnarAuditStore

from .conftest import make_entry, generate_entries


# ── Same interface tests as naive store ──

def test_append_and_count():
    store = ColumnarAuditStore()
    entries = generate_entries(100, base_ts=1_700_000_000.0)
    for e in entries:
        store.append(e)
    assert store.count() == 100


def test_query_time_range():
    store = ColumnarAuditStore()
    base = 1_700_000_000.0
    entries = generate_entries(1000, base_ts=base, span_s=86400.0)
    for e in entries:
        store.append(e)

    window_start = base + 6 * 3600
    window_end = base + 8 * 3600
    results = store.query_time_range(window_start, window_end)

    for r in results:
        assert window_start <= r.timestamp <= window_end

    expected = [e for e in entries if window_start <= e.timestamp <= window_end]
    assert len(results) == len(expected)


def test_query_time_range_empty():
    store = ColumnarAuditStore()
    base = 1_700_000_000.0
    entries = generate_entries(100, base_ts=base, span_s=3600.0)
    for e in entries:
        store.append(e)

    results = store.query_time_range(base + 100_000, base + 200_000)
    assert results == []


def test_query_time_range_all():
    store = ColumnarAuditStore()
    entries = generate_entries(50, base_ts=1_700_000_000.0, span_s=3600.0)
    for e in entries:
        store.append(e)

    results = store.query_time_range(0.0, 2_000_000_000.0)
    assert len(results) == 50


def test_query_by_agent():
    store = ColumnarAuditStore()
    target_agent = uuid.UUID(int=7)
    entries = generate_entries(500, base_ts=1_700_000_000.0)
    for e in entries:
        store.append(e)

    results = store.query_by_agent(target_agent)
    for r in results:
        assert r.agent_id == target_agent

    expected_count = sum(1 for e in entries if e.agent_id == target_agent)
    assert len(results) == expected_count


def test_query_by_domain():
    store = ColumnarAuditStore()
    entries = generate_entries(500, base_ts=1_700_000_000.0)
    for e in entries:
        store.append(e)

    target = "api.github.com"
    results = store.query_by_domain(target)
    for r in results:
        assert r.domain == target

    expected_count = sum(1 for e in entries if e.domain == target)
    assert len(results) == expected_count


def test_query_by_decision():
    store = ColumnarAuditStore()
    entries = generate_entries(500, base_ts=1_700_000_000.0)
    for e in entries:
        store.append(e)

    results = store.query_by_decision(AccessDecision.DENY)
    for r in results:
        assert r.decision == AccessDecision.DENY

    expected_count = sum(1 for e in entries if e.decision == AccessDecision.DENY)
    assert len(results) == expected_count


def test_empty_store():
    store = ColumnarAuditStore()
    assert store.count() == 0
    assert store.query_time_range(0.0, 1e18) == []
    assert store.query_by_agent(uuid.uuid4()) == []
    assert store.query_by_domain("nope.com") == []
    assert store.query_by_decision(AccessDecision.ALLOW) == []
    assert store.memory_usage_bytes() > 0


# ── Columnar-specific tests ──

def test_chronological_order_enforced():
    """Out-of-order append must raise ValueError."""
    store = ColumnarAuditStore()
    store.append(make_entry(ts=200.0))
    with pytest.raises(ValueError, match="Out-of-order"):
        store.append(make_entry(ts=100.0))


def test_equal_timestamps_allowed():
    """Same timestamp is fine (not strictly less-than)."""
    store = ColumnarAuditStore()
    store.append(make_entry(ts=100.0))
    store.append(make_entry(ts=100.0))  # should not raise
    assert store.count() == 2


def test_bisect_boundary_accuracy():
    """Range query boundaries are inclusive on both sides."""
    store = ColumnarAuditStore()
    timestamps = [10.0, 20.0, 30.0, 40.0, 50.0]
    for ts in timestamps:
        store.append(make_entry(ts=ts))

    # Query [20, 40] should return 20, 30, 40
    results = store.query_time_range(20.0, 40.0)
    result_ts = [r.timestamp for r in results]
    assert result_ts == [20.0, 30.0, 40.0]

    # Query [25, 35] should return only 30
    results = store.query_time_range(25.0, 35.0)
    assert len(results) == 1
    assert results[0].timestamp == 30.0

    # Query [10, 10] should return exactly the first entry
    results = store.query_time_range(10.0, 10.0)
    assert len(results) == 1
    assert results[0].timestamp == 10.0


def test_reconstruct_fidelity():
    """Round-trip: append an entry, query it back, all fields match.

    processing_time_ms uses array('f') (float32) so we allow a
    small tolerance on that field.
    """
    policy_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    original = make_entry(
        ts=1_700_000_500.0,
        agent_id=uuid.UUID(int=42),
        domain="api.stripe.com",
        decision=AccessDecision.DENY,
        reason="rate limit exceeded",
        method="POST",
        path="/v1/charges",
        source_ip="192.168.1.100",
        latency=12.345,
        policy_id=policy_id,
        rule_id=rule_id,
    )

    store = ColumnarAuditStore()
    store.append(original)

    results = store.query_time_range(1_700_000_000.0, 1_700_001_000.0)
    assert len(results) == 1
    got = results[0]

    assert got.entry_id == original.entry_id
    assert got.agent_id == original.agent_id
    assert got.domain == original.domain
    assert got.decision == original.decision
    assert got.timestamp == original.timestamp
    assert got.reason == original.reason
    assert got.policy_id == original.policy_id
    assert got.rule_id == original.rule_id
    assert got.request_method == original.request_method
    assert got.request_path == original.request_path
    assert got.source_ip == original.source_ip
    # float32 round-trip: allow small tolerance
    assert math.isclose(got.processing_time_ms, original.processing_time_ms, rel_tol=1e-3)


def test_reconstruct_none_policy():
    """Entries with policy_id=None and rule_id=None round-trip correctly."""
    original = make_entry(ts=100.0, policy_id=None, rule_id=None)
    store = ColumnarAuditStore()
    store.append(original)

    results = store.query_time_range(0.0, 200.0)
    assert len(results) == 1
    assert results[0].policy_id is None
    assert results[0].rule_id is None


def test_large_store_10k():
    """Insert 10K entries, verify count and a sample query.

    We use 10K here (not 1M) to keep the unit test fast.
    The 1M test lives in test_cache_benchmark.py.
    """
    store = ColumnarAuditStore()
    base = 1_700_000_000.0
    entries = generate_entries(10_000, base_ts=base, span_s=86400.0)
    for e in entries:
        store.append(e)

    assert store.count() == 10_000

    # Spot-check: 2h window should return roughly 10000 * (2/24) ~ 833 entries
    window_start = base + 6 * 3600
    window_end = base + 8 * 3600
    results = store.query_time_range(window_start, window_end)
    assert 500 < len(results) < 1200  # generous bounds for random distribution
