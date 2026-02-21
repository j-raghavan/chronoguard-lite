"""Shared fixtures for Chapter 8 tests."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

import pytest

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision

SEED = 42

DOMAINS = [
    "api.openai.com",
    "chat.openai.com",
    "api.stripe.com",
    "dashboard.stripe.com",
    "s3.amazonaws.com",
    "ec2.amazonaws.com",
    "graph.microsoft.com",
    "login.microsoft.com",
    "api.twilio.com",
    "api.pagerduty.com",
    "internal.corp.com",
    "staging.internal.corp.com",
    "api.staging.internal",
    "api.prod.internal",
    "cdn.example.com",
    "api.example.com",
    "mail.google.com",
    "drive.google.com",
    "api.github.com",
    "raw.githubusercontent.com",
]

REASONS = [
    "Policy matched: allow rule",
    "Policy matched: deny rule",
    "Rate limit exceeded for agent",
    "No matching policy found",
    "Request allowed by default",
    "Blocked by security policy",
    "Access denied: restricted domain",
    "Rate limit threshold reached",
]


def make_entry(
    domain: str | None = None,
    decision: AccessDecision = AccessDecision.ALLOW,
    reason: str = "Policy matched: allow rule",
    agent_id: uuid.UUID | None = None,
    timestamp: float | None = None,
) -> AuditEntry:
    """Create a test AuditEntry with sensible defaults."""
    now = timestamp or datetime.now(timezone.utc).timestamp()
    return AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=agent_id or uuid.uuid4(),
        domain=domain or "api.openai.com",
        decision=decision,
        timestamp=now,
        reason=reason,
        request_method="GET",
        request_path="/v1/chat",
        source_ip="10.0.0.1",
        processing_time_ms=1.5,
    )


def generate_entries(
    count: int, seed: int = SEED
) -> list[AuditEntry]:
    """Generate a batch of random AuditEntry objects."""
    rng = random.Random(seed)
    agents = [uuid.UUID(int=i) for i in range(50)]
    decisions = [AccessDecision.ALLOW, AccessDecision.DENY,
                 AccessDecision.RATE_LIMITED, AccessDecision.NO_MATCHING_POLICY]
    base_ts = 1700000000.0  # fixed base timestamp

    entries: list[AuditEntry] = []
    for i in range(count):
        entries.append(AuditEntry(
            entry_id=uuid.UUID(int=i + 1000000),
            agent_id=rng.choice(agents),
            domain=rng.choice(DOMAINS),
            decision=rng.choice(decisions),
            timestamp=base_ts + i * 0.01,  # 10ms apart
            reason=rng.choice(REASONS),
            request_method=rng.choice(["GET", "POST", "PUT", "DELETE"]),
            request_path=f"/v1/resource/{i}",
            source_ip=f"10.0.{i % 256}.{(i // 256) % 256}",
            processing_time_ms=rng.uniform(0.5, 10.0),
        ))
    return entries
