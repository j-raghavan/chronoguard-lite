"""Tests for NaiveAuditStore -- the list-based baseline."""
import uuid

import pytest

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.store.naive_store import NaiveAuditStore

from .conftest import make_entry, generate_entries


# ── append + count ──

def test_append_and_count():
    store = NaiveAuditStore()
    entries = generate_entries(100, base_ts=1_700_000_000.0)
    for e in entries:
        store.append(e)
    assert store.count() == 100


# ── time range queries ──

def test_query_time_range():
    """Insert 1000 entries over 24h, query a 2h window."""
    store = NaiveAuditStore()
    base = 1_700_000_000.0
    entries = generate_entries(1000, base_ts=base, span_s=86400.0)
    for e in entries:
        store.append(e)

    # 2h window starting 6h into the 24h span
    window_start = base + 6 * 3600
    window_end = base + 8 * 3600
    results = store.query_time_range(window_start, window_end)

    # Every result must be inside the window
    for r in results:
        assert window_start <= r.timestamp <= window_end

    # Cross-check: count entries in window manually
    expected = [e for e in entries if window_start <= e.timestamp <= window_end]
    assert len(results) == len(expected)


def test_query_time_range_empty():
    """Query a range with no entries returns []."""
    store = NaiveAuditStore()
    base = 1_700_000_000.0
    entries = generate_entries(100, base_ts=base, span_s=3600.0)
    for e in entries:
        store.append(e)

    # Query a range way after all entries
    results = store.query_time_range(base + 100_000, base + 200_000)
    assert results == []


def test_query_time_range_all():
    """Query the full range returns everything."""
    store = NaiveAuditStore()
    entries = generate_entries(50, base_ts=1_700_000_000.0, span_s=3600.0)
    for e in entries:
        store.append(e)

    results = store.query_time_range(0.0, 2_000_000_000.0)
    assert len(results) == 50


# ── filter queries ──

def test_query_by_agent():
    store = NaiveAuditStore()
    target_agent = uuid.UUID(int=7)  # from AGENT_POOL
    entries = generate_entries(500, base_ts=1_700_000_000.0)
    for e in entries:
        store.append(e)

    results = store.query_by_agent(target_agent)
    for r in results:
        assert r.agent_id == target_agent

    expected_count = sum(1 for e in entries if e.agent_id == target_agent)
    assert len(results) == expected_count


def test_query_by_domain():
    store = NaiveAuditStore()
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
    store = NaiveAuditStore()
    entries = generate_entries(500, base_ts=1_700_000_000.0)
    for e in entries:
        store.append(e)

    results = store.query_by_decision(AccessDecision.DENY)
    for r in results:
        assert r.decision == AccessDecision.DENY

    expected_count = sum(1 for e in entries if e.decision == AccessDecision.DENY)
    assert len(results) == expected_count


# ── edge case ──

def test_empty_store():
    store = NaiveAuditStore()
    assert store.count() == 0
    assert store.query_time_range(0.0, 1e18) == []
    assert store.query_by_agent(uuid.uuid4()) == []
    assert store.query_by_domain("nope.com") == []
    assert store.query_by_decision(AccessDecision.ALLOW) == []
    assert store.memory_usage_bytes() > 0  # at least the empty list overhead
