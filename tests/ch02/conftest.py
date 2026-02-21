"""Shared test fixtures for chapter 2 store tests."""
from __future__ import annotations

import random
import uuid

import pytest

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision


# Fixed seed so benchmark numbers are reproducible across runs
SEED = 42

# Pool of test values (realistic enough for a compliance platform)
AGENT_POOL = [uuid.UUID(int=i) for i in range(50)]
DOMAIN_POOL = [
    "api.openai.com", "api.anthropic.com", "graph.microsoft.com",
    "api.github.com", "api.stripe.com", "s3.amazonaws.com",
    "bigquery.googleapis.com", "api.slack.com", "api.twilio.com",
    "api.sendgrid.com", "cdn.jsdelivr.net", "registry.npmjs.org",
    "pypi.org", "hub.docker.com", "api.datadog.com",
    "api.pagerduty.com", "hooks.slack.com", "api.notion.com",
    "api.linear.app", "api.figma.com",
]
METHODS = ["GET", "POST", "PUT", "DELETE"]
DECISIONS = list(AccessDecision)


def make_entry(
    ts: float,
    agent_id: uuid.UUID | None = None,
    domain: str = "api.openai.com",
    decision: AccessDecision = AccessDecision.ALLOW,
    reason: str = "policy matched",
    method: str = "GET",
    path: str = "/v1/chat",
    source_ip: str = "10.0.0.1",
    latency: float = 1.5,
    policy_id: uuid.UUID | None = None,
    rule_id: uuid.UUID | None = None,
) -> AuditEntry:
    """Build an AuditEntry with a controlled timestamp.

    Skips AuditEntry.create() so we can pin the timestamp
    instead of getting time.time().
    """
    return AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=agent_id or uuid.uuid4(),
        domain=domain,
        decision=decision,
        timestamp=ts,
        reason=reason,
        policy_id=policy_id,
        rule_id=rule_id,
        request_method=method,
        request_path=path,
        source_ip=source_ip,
        processing_time_ms=latency,
    )


def generate_entries(n: int, base_ts: float = 1_700_000_000.0, span_s: float = 86400.0) -> list[AuditEntry]:
    """Generate n AuditEntry objects spread across `span_s` seconds.

    Entries are in chronological order (required by ColumnarAuditStore).
    Uses a fixed seed for reproducibility.
    """
    rng = random.Random(SEED)
    timestamps = sorted(base_ts + rng.random() * span_s for _ in range(n))
    entries = []
    for ts in timestamps:
        entries.append(make_entry(
            ts=ts,
            agent_id=rng.choice(AGENT_POOL),
            domain=rng.choice(DOMAIN_POOL),
            decision=rng.choice(DECISIONS),
            reason="auto-generated test entry",
            method=rng.choice(METHODS),
            path=f"/v1/{rng.choice(['chat', 'embeddings', 'completions', 'models'])}",
            source_ip=f"10.0.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
            latency=rng.uniform(0.5, 50.0),
        ))
    return entries
