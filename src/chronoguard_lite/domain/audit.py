"""AuditEntry — immutable record of every access decision.

Each entry records: who (agent), what (domain), when (timestamp),
why (decision + reason), and how (which policy/rule matched).

The entry is immutable after creation. Hash chaining is added in Chapter 6.

Mapped from full ChronoGuard: domain/audit/entity.py
Simplified: no tenant_id, no TimedAccessContext, no signature field.
"""
from __future__ import annotations

import time as time_module
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.types import AgentId, DomainName, EntryId, PolicyId


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Immutable audit log entry.

    frozen=True ensures no field can be modified after creation.
    slots=True reduces memory overhead (~180 bytes vs ~400 bytes).
    """
    entry_id: EntryId
    agent_id: AgentId
    domain: DomainName
    decision: AccessDecision
    timestamp: float                        # Unix epoch seconds (time.time())
    reason: str                             # Human-readable decision reason
    policy_id: PolicyId | None = None       # Which policy matched (None = no match)
    rule_id: uuid.UUID | None = None        # Which rule within the policy
    request_method: str = "GET"             # HTTP method
    request_path: str = "/"                 # Request path
    source_ip: str = "0.0.0.0"             # Client IP
    processing_time_ms: float = 0.0         # Latency in milliseconds

    @classmethod
    def create(
        cls,
        agent_id: AgentId,
        domain: DomainName,
        decision: AccessDecision,
        reason: str,
        policy_id: PolicyId | None = None,
        rule_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> AuditEntry:
        """Factory: create an audit entry with auto-generated ID and timestamp."""
        return cls(
            entry_id=uuid.uuid4(),
            agent_id=agent_id,
            domain=domain,
            decision=decision,
            timestamp=time_module.time(),
            reason=reason,
            policy_id=policy_id,
            rule_id=rule_id,
            **kwargs,
        )

    def is_permitted(self) -> bool:
        """Was access allowed?"""
        return self.decision == AccessDecision.ALLOW

    @property
    def datetime_utc(self) -> datetime:
        """Convert Unix timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    @property
    def hour_of_day(self) -> int:
        """Hour component (0-23) for temporal analytics."""
        return self.datetime_utc.hour

    @property
    def day_of_week(self) -> int:
        """Day of week (0=Monday, 6=Sunday)."""
        return self.datetime_utc.weekday()

    @property
    def is_business_hours(self) -> bool:
        """True if timestamp falls within 9 AM - 5 PM UTC."""
        return 9 <= self.hour_of_day < 17
