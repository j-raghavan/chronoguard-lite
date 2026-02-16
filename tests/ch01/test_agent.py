"""Tests for Agent entity and state machine."""
import uuid
from datetime import datetime, timezone

import pytest

from chronoguard_lite.domain.agent import (
    Agent,
    AgentStatus,
    InvalidTransition,
    VALID_TRANSITIONS,
)


def test_create_agent():
    agent = Agent.create("test-agent")
    assert agent.name == "test-agent"
    assert agent.status == AgentStatus.PENDING
    assert isinstance(agent.agent_id, uuid.UUID)
    assert isinstance(agent.created_at, datetime)
    assert isinstance(agent.updated_at, datetime)
    assert agent.policy_ids == []
    assert agent.last_seen_at is None
    assert agent.metadata == {}


def test_activate():
    agent = Agent.create("test-agent")
    old_updated = agent.updated_at
    agent.activate()
    assert agent.status == AgentStatus.ACTIVE
    assert agent.updated_at >= old_updated


def test_suspend():
    agent = Agent.create("test-agent")
    agent.activate()
    agent.suspend()
    assert agent.status == AgentStatus.SUSPENDED


def test_reactivate():
    agent = Agent.create("test-agent")
    agent.activate()
    agent.suspend()
    agent.activate()
    assert agent.status == AgentStatus.ACTIVE


def test_invalid_transition_deactivated():
    agent = Agent.create("test-agent")
    agent.activate()
    agent.deactivate()
    with pytest.raises(InvalidTransition, match="DEACTIVATED.*ACTIVE"):
        agent.activate()


def test_invalid_transition_expired():
    agent = Agent.create("test-agent")
    agent.activate()
    agent.mark_expired()
    for method in [agent.activate, agent.suspend, agent.deactivate, agent.mark_expired]:
        with pytest.raises(InvalidTransition):
            method()


def test_all_valid_transitions():
    """Walk every edge in VALID_TRANSITIONS map."""
    for from_status, to_statuses in VALID_TRANSITIONS.items():
        for to_status in to_statuses:
            agent = Agent.create("test")
            # Get agent into from_status
            if from_status == AgentStatus.ACTIVE:
                agent.activate()
            elif from_status == AgentStatus.SUSPENDED:
                agent.activate()
                agent.suspend()
            elif from_status == AgentStatus.DEACTIVATED:
                agent.activate()
                agent.deactivate()
            elif from_status == AgentStatus.EXPIRED:
                agent.activate()
                agent.mark_expired()
            # Now try the transition
            agent._transition_to(to_status)
            assert agent.status == to_status


def test_assign_policy():
    agent = Agent.create("test-agent")
    pid = uuid.uuid4()
    agent.assign_policy(pid)
    assert pid in agent.policy_ids


def test_assign_duplicate_policy():
    agent = Agent.create("test-agent")
    pid = uuid.uuid4()
    agent.assign_policy(pid)
    with pytest.raises(ValueError, match="already assigned"):
        agent.assign_policy(pid)


def test_assign_max_policies():
    agent = Agent.create("test-agent")
    for _ in range(50):
        agent.assign_policy(uuid.uuid4())
    with pytest.raises(ValueError, match="Maximum 50"):
        agent.assign_policy(uuid.uuid4())


def test_remove_policy():
    agent = Agent.create("test-agent")
    pid = uuid.uuid4()
    agent.assign_policy(pid)
    agent.remove_policy(pid)
    assert pid not in agent.policy_ids


def test_remove_nonexistent_policy():
    agent = Agent.create("test-agent")
    with pytest.raises(ValueError, match="not found"):
        agent.remove_policy(uuid.uuid4())


def test_can_make_requests_active():
    agent = Agent.create("test-agent")
    agent.activate()
    assert agent.can_make_requests() is True


def test_can_make_requests_inactive():
    for status in [AgentStatus.PENDING, AgentStatus.SUSPENDED,
                   AgentStatus.DEACTIVATED, AgentStatus.EXPIRED]:
        agent = Agent.create("test")
        # Force status directly for test simplicity
        agent.status = status
        assert agent.can_make_requests() is False


def test_touch_updates_last_seen():
    agent = Agent.create("test-agent")
    assert agent.last_seen_at is None
    agent.touch()
    assert agent.last_seen_at is not None
    assert isinstance(agent.last_seen_at, datetime)
    assert agent.last_seen_at.tzinfo == timezone.utc
