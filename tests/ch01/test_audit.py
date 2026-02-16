"""Tests for AuditEntry — immutable audit log records."""
import time
import uuid
from datetime import datetime, timezone

import pytest

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision


# ── Creation ──

def test_create_audit_entry():
    agent_id = uuid.uuid4()
    entry = AuditEntry.create(
        agent_id=agent_id,
        domain="api.openai.com",
        decision=AccessDecision.ALLOW,
        reason="Rule matched",
    )
    assert entry.agent_id == agent_id
    assert entry.domain == "api.openai.com"
    assert entry.decision == AccessDecision.ALLOW
    assert entry.reason == "Rule matched"
    assert isinstance(entry.entry_id, uuid.UUID)
    assert isinstance(entry.timestamp, float)


def test_create_with_optional_fields():
    policy_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    entry = AuditEntry.create(
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.DENY,
        reason="Blocked",
        policy_id=policy_id,
        rule_id=rule_id,
        request_method="POST",
        request_path="/api/v1/data",
        source_ip="192.168.1.1",
        processing_time_ms=3.5,
    )
    assert entry.policy_id == policy_id
    assert entry.rule_id == rule_id
    assert entry.request_method == "POST"
    assert entry.request_path == "/api/v1/data"
    assert entry.source_ip == "192.168.1.1"
    assert entry.processing_time_ms == 3.5


# ── Immutability ──

def test_frozen():
    entry = AuditEntry.create(
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.ALLOW,
        reason="OK",
    )
    with pytest.raises(AttributeError):
        entry.domain = "other.com"  # type: ignore[misc]


# ── is_permitted ──

def test_is_permitted_allow():
    entry = AuditEntry.create(
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.ALLOW,
        reason="OK",
    )
    assert entry.is_permitted() is True


def test_is_permitted_deny():
    entry = AuditEntry.create(
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.DENY,
        reason="Blocked",
    )
    assert entry.is_permitted() is False


def test_is_permitted_rate_limited():
    entry = AuditEntry.create(
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.RATE_LIMITED,
        reason="Too many requests",
    )
    assert entry.is_permitted() is False


# ── Temporal properties ──

def test_datetime_utc():
    entry = AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.ALLOW,
        timestamp=1736337600.0,  # 2025-01-08 12:00:00 UTC
        reason="OK",
    )
    dt = entry.datetime_utc
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2025
    assert dt.month == 1
    assert dt.day == 8
    assert dt.hour == 12


def test_hour_of_day():
    entry = AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.ALLOW,
        timestamp=1736337600.0,  # 2025-01-08 12:00:00 UTC
        reason="OK",
    )
    assert entry.hour_of_day == 12


def test_day_of_week():
    # 2025-01-08 is a Wednesday (weekday=2)
    entry = AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.ALLOW,
        timestamp=1736337600.0,  # 2025-01-08 12:00:00 UTC (Wednesday)
        reason="OK",
    )
    assert entry.day_of_week == 2  # Wednesday


def test_is_business_hours_true():
    # 12:00 UTC — within 9-17
    entry = AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.ALLOW,
        timestamp=1736337600.0,  # 2025-01-08 12:00:00 UTC
        reason="OK",
    )
    assert entry.is_business_hours is True


def test_is_business_hours_false():
    # 20:00 UTC — outside 9-17
    entry = AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        domain="example.com",
        decision=AccessDecision.ALLOW,
        timestamp=1736366400.0,  # 2025-01-08 20:00:00 UTC
        reason="OK",
    )
    assert entry.is_business_hours is False
