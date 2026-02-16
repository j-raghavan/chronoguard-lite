"""Tests for Policy, PolicyRule, TimeWindow, RateLimit."""
import uuid
from datetime import datetime, time, timezone

import pytest

from chronoguard_lite.domain.policy import (
    Policy,
    PolicyRule,
    PolicyStatus,
    RateLimit,
    RuleAction,
    TimeWindow,
)


# ── PolicyRule matching ──

def test_evaluate_exact_match():
    rule = PolicyRule.allow("api.openai.com")
    assert rule.matches("api.openai.com") is True


def test_evaluate_exact_no_match():
    rule = PolicyRule.allow("api.openai.com")
    assert rule.matches("chat.openai.com") is False


def test_evaluate_wildcard_prefix():
    rule = PolicyRule.allow("*.openai.com")
    assert rule.matches("api.openai.com") is True
    assert rule.matches("chat.openai.com") is True


def test_evaluate_wildcard_prefix_no_match():
    rule = PolicyRule.allow("*.openai.com")
    assert rule.matches("openai.com") is False  # Different segment count


def test_evaluate_wildcard_segment():
    rule = PolicyRule.allow("api.*.internal")
    assert rule.matches("api.staging.internal") is True
    assert rule.matches("api.prod.internal") is True


def test_evaluate_wildcard_segment_no_match():
    rule = PolicyRule.allow("api.*.internal")
    assert rule.matches("web.staging.internal") is False


def test_rule_factories():
    allow_rule = PolicyRule.allow("example.com", priority=50)
    assert allow_rule.action == RuleAction.ALLOW
    assert allow_rule.priority == 50
    deny_rule = PolicyRule.deny("evil.com", priority=10)
    assert deny_rule.action == RuleAction.DENY
    assert deny_rule.priority == 10


# ── Policy lifecycle ──

def test_create_policy():
    policy = Policy.create("test-policy")
    assert policy.name == "test-policy"
    assert policy.status == PolicyStatus.DRAFT
    assert policy.rules == []
    assert isinstance(policy.policy_id, uuid.UUID)


def test_activate_with_rules():
    policy = Policy.create("test")
    policy.add_rule(PolicyRule.allow("example.com"))
    policy.activate()
    assert policy.status == PolicyStatus.ACTIVE


def test_activate_no_rules():
    policy = Policy.create("test")
    with pytest.raises(ValueError, match="no rules"):
        policy.activate()


def test_activate_non_draft():
    policy = Policy.create("test")
    policy.add_rule(PolicyRule.allow("example.com"))
    policy.activate()
    with pytest.raises(ValueError, match="DRAFT"):
        policy.activate()


def test_suspend():
    policy = Policy.create("test")
    policy.add_rule(PolicyRule.allow("example.com"))
    policy.activate()
    policy.suspend()
    assert policy.status == PolicyStatus.SUSPENDED


def test_suspend_non_active():
    policy = Policy.create("test")
    with pytest.raises(ValueError, match="ACTIVE"):
        policy.suspend()


def test_archive_from_any():
    for start_status in [PolicyStatus.DRAFT, PolicyStatus.ACTIVE, PolicyStatus.SUSPENDED]:
        policy = Policy.create("test")
        if start_status in (PolicyStatus.ACTIVE, PolicyStatus.SUSPENDED):
            policy.add_rule(PolicyRule.allow("example.com"))
            policy.activate()
        if start_status == PolicyStatus.SUSPENDED:
            policy.suspend()
        policy.archive()
        assert policy.status == PolicyStatus.ARCHIVED


def test_archive_already_archived():
    policy = Policy.create("test")
    policy.archive()
    with pytest.raises(ValueError, match="already archived"):
        policy.archive()


# ── Rules management ──

def test_add_rule():
    policy = Policy.create("test")
    rule = PolicyRule.allow("example.com")
    policy.add_rule(rule)
    assert len(policy.rules) == 1
    assert policy.rules[0] is rule


def test_add_max_rules():
    policy = Policy.create("test")
    for _ in range(100):
        policy.add_rule(PolicyRule.allow("example.com"))
    with pytest.raises(ValueError, match="Maximum 100"):
        policy.add_rule(PolicyRule.allow("example.com"))


def test_remove_rule():
    policy = Policy.create("test")
    rule = PolicyRule.allow("example.com")
    policy.add_rule(rule)
    policy.remove_rule(rule.rule_id)
    assert len(policy.rules) == 0


def test_remove_nonexistent_rule():
    policy = Policy.create("test")
    with pytest.raises(ValueError, match="not found"):
        policy.remove_rule(uuid.uuid4())


# ── Policy evaluation ──

def test_evaluate_no_match():
    policy = Policy.create("test")
    policy.add_rule(PolicyRule.allow("api.openai.com"))
    result = policy.evaluate("google.com", datetime.now(timezone.utc))
    assert result is None


def test_evaluate_priority_ordering():
    policy = Policy.create("test")
    policy.add_rule(PolicyRule.deny("api.openai.com", priority=50))
    policy.add_rule(PolicyRule.allow("api.openai.com", priority=10))  # Higher priority
    result = policy.evaluate("api.openai.com", datetime.now(timezone.utc))
    assert result == RuleAction.ALLOW


def test_evaluate_deny_overrides_allow():
    policy = Policy.create("test")
    policy.add_rule(PolicyRule.allow("api.openai.com", priority=50))
    policy.add_rule(PolicyRule.deny("api.openai.com", priority=10))  # Higher priority
    result = policy.evaluate("api.openai.com", datetime.now(timezone.utc))
    assert result == RuleAction.DENY


# ── TimeWindow ──

def test_time_window_inside():
    tw = TimeWindow(
        start_time=time(9, 0),
        end_time=time(17, 0),
        days_of_week={0, 1, 2, 3, 4},  # Monday-Friday
    )
    # Wednesday at 12:00 UTC
    dt = datetime(2025, 1, 8, 12, 0, tzinfo=timezone.utc)
    assert tw.contains(dt) is True


def test_time_window_outside():
    tw = TimeWindow(
        start_time=time(9, 0),
        end_time=time(17, 0),
        days_of_week={0, 1, 2, 3, 4},
    )
    # Wednesday at 20:00 UTC (after hours)
    dt = datetime(2025, 1, 8, 20, 0, tzinfo=timezone.utc)
    assert tw.contains(dt) is False


def test_time_window_wrong_day():
    tw = TimeWindow(
        start_time=time(9, 0),
        end_time=time(17, 0),
        days_of_week={0, 1, 2, 3, 4},  # Weekdays only
    )
    # Saturday at 12:00 UTC
    dt = datetime(2025, 1, 11, 12, 0, tzinfo=timezone.utc)
    assert tw.contains(dt) is False


def test_time_window_overnight():
    tw = TimeWindow(
        start_time=time(22, 0),
        end_time=time(6, 0),
        days_of_week={0, 1, 2, 3, 4, 5, 6},
    )
    # 23:00 — inside
    dt_late = datetime(2025, 1, 8, 23, 0, tzinfo=timezone.utc)
    assert tw.contains(dt_late) is True
    # 03:00 — inside
    dt_early = datetime(2025, 1, 8, 3, 0, tzinfo=timezone.utc)
    assert tw.contains(dt_early) is True
    # 12:00 — outside
    dt_mid = datetime(2025, 1, 8, 12, 0, tzinfo=timezone.utc)
    assert tw.contains(dt_mid) is False


def test_evaluate_time_window_outside():
    policy = Policy.create("test")
    policy.add_rule(PolicyRule.allow("api.openai.com"))
    policy.time_window = TimeWindow(
        start_time=time(9, 0),
        end_time=time(17, 0),
        days_of_week={0, 1, 2, 3, 4},
    )
    # 20:00 — outside business hours
    dt = datetime(2025, 1, 8, 20, 0, tzinfo=timezone.utc)
    assert policy.evaluate("api.openai.com", dt) is None


# ── RateLimit ──

def test_rate_limit_validation():
    with pytest.raises(ValueError, match="per_minute <= per_hour <= per_day"):
        RateLimit(requests_per_minute=100, requests_per_hour=50, requests_per_day=1000)


def test_rate_limit_valid():
    rl = RateLimit(requests_per_minute=10, requests_per_hour=100, requests_per_day=1000)
    assert rl.requests_per_minute == 10


def test_rate_limit_burst_limit_validation():
    with pytest.raises(ValueError, match="burst_limit"):
        RateLimit(requests_per_minute=10, requests_per_hour=100, requests_per_day=1000, burst_limit=0)


def test_check_rate_limit_within():
    policy = Policy.create("test")
    policy.rate_limit = RateLimit(
        requests_per_minute=10, requests_per_hour=100, requests_per_day=1000
    )
    assert policy.check_rate_limit(5, "minute") is True


def test_check_rate_limit_exceeded():
    policy = Policy.create("test")
    policy.rate_limit = RateLimit(
        requests_per_minute=10, requests_per_hour=100, requests_per_day=1000
    )
    assert policy.check_rate_limit(15, "minute") is False


def test_check_rate_limit_no_limit():
    policy = Policy.create("test")
    assert policy.check_rate_limit(999999, "minute") is True


def test_check_rate_limit_invalid_window():
    policy = Policy.create("test")
    policy.rate_limit = RateLimit(
        requests_per_minute=10, requests_per_hour=100, requests_per_day=1000
    )
    with pytest.raises(ValueError, match="Unknown window"):
        policy.check_rate_limit(5, "week")
