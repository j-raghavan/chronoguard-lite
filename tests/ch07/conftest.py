"""Shared helpers for chapter 7 analytics tests."""
from __future__ import annotations

import random
import uuid

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision


SEED = 42

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
) -> AuditEntry:
    return AuditEntry(
        entry_id=uuid.uuid4(),
        agent_id=agent_id or uuid.uuid4(),
        domain=domain,
        decision=decision,
        timestamp=ts,
        reason="auto-generated test entry",
        request_method="GET",
        request_path="/v1/chat",
        source_ip="10.0.0.1",
        processing_time_ms=1.5,
    )


def generate_entries(
    n: int,
    base_ts: float = 1_700_000_000.0,
    span_s: float = 86400.0,
) -> list[AuditEntry]:
    rng = random.Random(SEED)
    timestamps = sorted(base_ts + rng.random() * span_s for _ in range(n))
    entries = []
    for ts in timestamps:
        entries.append(make_entry(
            ts=ts,
            agent_id=rng.choice(AGENT_POOL),
            domain=rng.choice(DOMAIN_POOL),
            decision=rng.choice(DECISIONS),
        ))
    return entries
