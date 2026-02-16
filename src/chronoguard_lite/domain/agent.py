"""Agent entity — the AI agent being monitored.

Three implementations for memory comparison:
  1. AgentDataclass — @dataclass (naive, ~400 bytes/instance)
  2. AgentSlots — @dataclass with __slots__ (~200 bytes/instance)
  3. Agent — Final production version with __slots__ + state machine
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

from chronoguard_lite.domain.types import AgentId, PolicyId


class AgentStatus(Enum):
    PENDING = auto()
    ACTIVE = auto()
    SUSPENDED = auto()
    DEACTIVATED = auto()
    EXPIRED = auto()


class InvalidTransition(Exception):
    """Raised when an agent state transition is not allowed."""


# --- Version 1: Naive dataclass (for memory comparison) ---

@dataclass
class AgentDataclass:
    agent_id: AgentId
    name: str
    status: AgentStatus
    policy_ids: list[PolicyId]
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --- Version 2: Dataclass with __slots__ (for memory comparison) ---

@dataclass(slots=True)
class AgentSlots:
    agent_id: AgentId
    name: str
    status: AgentStatus
    policy_ids: list[PolicyId]
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --- Version 3: Production version with state machine ---

VALID_TRANSITIONS: dict[AgentStatus, set[AgentStatus]] = {
    AgentStatus.PENDING: {AgentStatus.ACTIVE, AgentStatus.DEACTIVATED},
    AgentStatus.ACTIVE: {AgentStatus.SUSPENDED, AgentStatus.DEACTIVATED, AgentStatus.EXPIRED},
    AgentStatus.SUSPENDED: {AgentStatus.ACTIVE, AgentStatus.DEACTIVATED},
    AgentStatus.DEACTIVATED: set(),
    AgentStatus.EXPIRED: set(),
}


@dataclass(slots=True)
class Agent:
    """Production agent entity with lifecycle state machine.

    State transitions:
        PENDING → ACTIVE → SUSPENDED ↔ ACTIVE
                        ↘ DEACTIVATED
                        ↘ EXPIRED
    """
    agent_id: AgentId
    name: str
    status: AgentStatus
    policy_ids: list[PolicyId]
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, name: str) -> Agent:
        """Factory: create a new agent in PENDING state."""
        now = datetime.now(timezone.utc)
        return cls(
            agent_id=uuid.uuid4(),
            name=name,
            status=AgentStatus.PENDING,
            policy_ids=[],
            created_at=now,
            updated_at=now,
        )

    def activate(self) -> None:
        """Transition to ACTIVE. Raises InvalidTransition if not allowed."""
        self._transition_to(AgentStatus.ACTIVE)

    def suspend(self) -> None:
        """Transition to SUSPENDED."""
        self._transition_to(AgentStatus.SUSPENDED)

    def deactivate(self) -> None:
        """Transition to DEACTIVATED (terminal)."""
        self._transition_to(AgentStatus.DEACTIVATED)

    def mark_expired(self) -> None:
        """Transition to EXPIRED (terminal)."""
        self._transition_to(AgentStatus.EXPIRED)

    def assign_policy(self, policy_id: PolicyId) -> None:
        """Assign a policy. Raises ValueError if already assigned or limit reached.

        Max 50 policies per agent.
        """
        if policy_id in self.policy_ids:
            raise ValueError(f"Policy {policy_id} already assigned to agent {self.agent_id}")
        if len(self.policy_ids) >= 50:
            raise ValueError("Maximum 50 policies per agent")
        self.policy_ids.append(policy_id)

    def remove_policy(self, policy_id: PolicyId) -> None:
        """Remove an assigned policy. Raises ValueError if not found."""
        try:
            self.policy_ids.remove(policy_id)
        except ValueError:
            raise ValueError(
                f"Policy {policy_id} not found in agent {self.agent_id}"
            ) from None

    def can_make_requests(self) -> bool:
        """Only ACTIVE agents can make requests."""
        return self.status == AgentStatus.ACTIVE

    def touch(self) -> None:
        """Update last_seen_at to now."""
        self.last_seen_at = datetime.now(timezone.utc)

    def _transition_to(self, new_status: AgentStatus) -> None:
        """Validate and execute state transition."""
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InvalidTransition(
                f"Cannot transition from {self.status.name} to {new_status.name}"
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
