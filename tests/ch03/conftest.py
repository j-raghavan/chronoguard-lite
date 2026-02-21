"""Shared fixtures for Chapter 3 tests.

Provides pre-built agents, policies, and helper functions for spinning
up the ThreadedInterceptor in a background thread.
"""
from __future__ import annotations

import socket
import threading
import uuid
from datetime import datetime, time, timezone

import pytest

from chronoguard_lite.domain.agent import Agent, AgentStatus
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import (
    Policy,
    PolicyRule,
    PolicyStatus,
    RuleAction,
    TimeWindow,
)
from chronoguard_lite.interceptor.protocol import (
    InterceptRequest,
    InterceptResponse,
    read_message,
    write_message,
)
from chronoguard_lite.interceptor.threaded import ThreadedInterceptor
from chronoguard_lite.store.columnar_store import ColumnarAuditStore


# ---------------------------------------------------------------------------
# Domain fixtures
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
    time_window: TimeWindow | None = None,
) -> Policy:
    p = Policy.create(name=name, priority=priority)
    for r in rules:
        p.add_rule(r)
    p.time_window = time_window
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
def business_hours_policy() -> Policy:
    """Policy that only allows during Mon-Fri 09:00-17:00 UTC."""
    return _make_policy(
        "business-hours",
        priority=20,
        rules=[PolicyRule.allow("*.internal.corp", priority=10)],
        time_window=TimeWindow(
            start_time=time(9, 0),
            end_time=time(17, 0),
            days_of_week={0, 1, 2, 3, 4},  # Mon-Fri
        ),
    )


@pytest.fixture()
def active_agent(allow_openai_policy, deny_malware_policy) -> Agent:
    return _make_agent(
        "test-agent",
        AgentStatus.ACTIVE,
        [allow_openai_policy.policy_id, deny_malware_policy.policy_id],
    )


@pytest.fixture()
def suspended_agent(allow_openai_policy) -> Agent:
    return _make_agent(
        "suspended-agent",
        AgentStatus.SUSPENDED,
        [allow_openai_policy.policy_id],
    )


# ---------------------------------------------------------------------------
# Server fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def audit_store() -> ColumnarAuditStore:
    return ColumnarAuditStore()


@pytest.fixture()
def server_factory():
    """Factory that creates and starts a ThreadedInterceptor in a background thread.

    Returns a callable that accepts (agents, policies, audit_store, max_workers)
    and returns (interceptor, (host, port)).

    The server is automatically stopped after the test.
    """
    servers: list[ThreadedInterceptor] = []

    def _create(
        agents: dict[str, Agent],
        policies: dict[str, Policy],
        audit_store: ColumnarAuditStore,
        max_workers: int = 4,
    ) -> tuple[ThreadedInterceptor, tuple[str, int]]:
        srv = ThreadedInterceptor(
            host="127.0.0.1",
            port=0,  # OS picks a free port
            max_workers=max_workers,
            agents=agents,
            policies=policies,
            audit_store=audit_store,
        )
        t = threading.Thread(target=srv.start, daemon=True)
        t.start()
        srv.wait_ready(timeout=5.0)
        # Small sleep to let the socket bind complete
        import time as _time
        _time.sleep(0.05)
        servers.append(srv)
        return srv, srv.address

    yield _create

    for s in servers:
        s.stop()


def send_request(
    host: str,
    port: int,
    req: InterceptRequest,
    timeout: float = 5.0,
) -> InterceptResponse:
    """Send a single request to the interceptor and return the response.

    Opens a new TCP connection each time (connection-per-request model,
    matching the interceptor's design).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        # Send request
        req_bytes = req.to_bytes()
        sock.sendall(req_bytes)
        # Read response
        resp_data = read_message(sock)
        return InterceptResponse.from_bytes(resp_data)
    finally:
        sock.close()
