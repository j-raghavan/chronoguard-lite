"""Shared fixtures for Chapter 5 async interceptor tests.

Reuses domain fixtures from ch03 (agents, policies) and adds
async-specific helpers for starting/stopping the AsyncInterceptor.

Requires: pip install pytest-asyncio
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from chronoguard_lite.domain.agent import Agent, AgentStatus
from chronoguard_lite.domain.policy import (
    Policy,
    PolicyRule,
    PolicyStatus,
)
from chronoguard_lite.interceptor.async_interceptor import AsyncInterceptor
from chronoguard_lite.interceptor.async_protocol import async_read_message
from chronoguard_lite.interceptor.protocol import InterceptRequest, InterceptResponse
from chronoguard_lite.store.columnar_store import ColumnarAuditStore


# ---------------------------------------------------------------------------
# Domain fixtures (same as ch03, duplicated to keep ch05 self-contained)
# ---------------------------------------------------------------------------

def _make_agent(name: str, status: AgentStatus, policy_ids: list[uuid.UUID]) -> Agent:
    now = datetime.now(timezone.utc)
    return Agent(
        agent_id=uuid.uuid4(),
        name=name,
        status=status,
        policy_ids=list(policy_ids),
        created_at=now,
        updated_at=now,
    )


def _make_policy(
    name: str,
    priority: int,
    rules: list[PolicyRule],
) -> Policy:
    p = Policy.create(name=name, priority=priority)
    for r in rules:
        p.add_rule(r)
    p.status = PolicyStatus.ACTIVE
    return p


@pytest.fixture()
def allow_openai_policy() -> Policy:
    return _make_policy(
        "allow-openai",
        priority=10,
        rules=[PolicyRule.allow("api.openai.com", priority=10)],
    )


@pytest.fixture()
def deny_malware_policy() -> Policy:
    return _make_policy(
        "deny-malware",
        priority=5,
        rules=[PolicyRule.deny("malware.example.com", priority=10)],
    )


@pytest.fixture()
def active_agent(allow_openai_policy, deny_malware_policy) -> Agent:
    return _make_agent(
        "test-agent",
        AgentStatus.ACTIVE,
        [allow_openai_policy.policy_id, deny_malware_policy.policy_id],
    )


@pytest.fixture()
def audit_store() -> ColumnarAuditStore:
    return ColumnarAuditStore()


# ---------------------------------------------------------------------------
# Async server helpers
# ---------------------------------------------------------------------------

async def start_async_server(
    agents: dict[str, Agent],
    policies: dict[str, Policy],
    audit_store: ColumnarAuditStore,
    queue_maxsize: int = 50_000,
) -> AsyncInterceptor:
    """Create and start an AsyncInterceptor, wait until ready."""
    srv = AsyncInterceptor(
        host="127.0.0.1",
        port=0,
        agents=agents,
        policies=policies,
        audit_store=audit_store,
        queue_maxsize=queue_maxsize,
    )
    await srv.start()
    await srv.wait_ready()
    return srv


async def async_send_request(
    host: str,
    port: int,
    req: InterceptRequest,
) -> InterceptResponse:
    """Send a single request to the async interceptor and return the response."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        # Send: length-prefixed request
        req_bytes = req.to_bytes()
        writer.write(req_bytes)
        await writer.drain()
        # Read: length-prefixed response
        resp_data = await async_read_message(reader)
        return InterceptResponse.from_bytes(resp_data)
    finally:
        writer.close()
        await writer.wait_closed()
