"""Tests for AccessDecision enum."""
from chronoguard_lite.domain.decisions import AccessDecision


def test_allow_is_permitted():
    assert AccessDecision.ALLOW.is_permitted() is True


def test_deny_is_not_permitted():
    assert AccessDecision.DENY.is_permitted() is False


def test_rate_limited_is_not_permitted():
    assert AccessDecision.RATE_LIMITED.is_permitted() is False


def test_no_matching_policy_is_not_permitted():
    assert AccessDecision.NO_MATCHING_POLICY.is_permitted() is False


def test_enum_members_exist():
    assert len(AccessDecision) == 4
    names = {d.name for d in AccessDecision}
    assert names == {"ALLOW", "DENY", "RATE_LIMITED", "NO_MATCHING_POLICY"}
