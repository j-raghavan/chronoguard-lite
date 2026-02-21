"""Tests for the ThreadedInterceptor.

Covers: single request, concurrent load, unknown agent handling,
audit entry creation, graceful shutdown, and request counter.

Each test spins up a server on an OS-assigned port, runs the scenario,
and tears down. The server_factory fixture handles cleanup.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.interceptor.protocol import InterceptRequest
from chronoguard_lite.store.columnar_store import ColumnarAuditStore

from tests.ch03.conftest import send_request


def _build_registries(agent, *policies):
    """Build the agents/policies dicts expected by ThreadedInterceptor."""
    agents = {str(agent.agent_id): agent}
    pol_dict = {str(p.policy_id): p for p in policies}
    return agents, pol_dict


def test_single_request(
    server_factory, audit_store, active_agent, allow_openai_policy, deny_malware_policy
):
    """Start server, send one request, get correct response."""
    agents, policies = _build_registries(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv, (host, port) = server_factory(agents, policies, audit_store)

    req = InterceptRequest(
        agent_id=str(active_agent.agent_id),
        domain="api.openai.com",
        method="POST",
        path="/v1/chat/completions",
        source_ip="10.0.0.5",
    )
    resp = send_request(host, port, req)
    assert resp.decision == "ALLOW"
    assert resp.processing_time_ms > 0


def test_concurrent_100(
    server_factory, audit_store, active_agent, allow_openai_policy, deny_malware_policy
):
    """100 concurrent clients all get correct responses."""
    agents, policies = _build_registries(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv, (host, port) = server_factory(agents, policies, audit_store, max_workers=8)

    n_clients = 100
    req = InterceptRequest(
        agent_id=str(active_agent.agent_id),
        domain="api.openai.com",
        method="GET",
        path="/v1/models",
    )

    results = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futs = [pool.submit(send_request, host, port, req) for _ in range(n_clients)]
        for f in as_completed(futs):
            results.append(f.result())

    assert len(results) == n_clients
    assert all(r.decision == "ALLOW" for r in results)


def test_unknown_agent(
    server_factory, audit_store, active_agent, allow_openai_policy
):
    """Request from an unregistered agent gets DENY."""
    agents, policies = _build_registries(active_agent, allow_openai_policy)
    srv, (host, port) = server_factory(agents, policies, audit_store)

    req = InterceptRequest(
        agent_id=str(uuid.uuid4()),  # not registered
        domain="api.openai.com",
        method="GET",
        path="/",
    )
    resp = send_request(host, port, req)
    assert resp.decision == "DENY"
    assert "Unknown agent" in resp.reason


def test_audit_entry_created(
    server_factory, audit_store, active_agent, allow_openai_policy, deny_malware_policy
):
    """After a request, the audit store has a new entry."""
    agents, policies = _build_registries(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv, (host, port) = server_factory(agents, policies, audit_store)

    assert audit_store.count() == 0

    req = InterceptRequest(
        agent_id=str(active_agent.agent_id),
        domain="api.openai.com",
        method="POST",
        path="/v1/chat/completions",
    )
    send_request(host, port, req)

    # Give the server thread a moment to finish audit logging
    time.sleep(0.1)
    assert audit_store.count() == 1


def test_graceful_shutdown(
    server_factory, audit_store, active_agent, allow_openai_policy
):
    """stop() while requests may be in flight does not crash."""
    agents, policies = _build_registries(active_agent, allow_openai_policy)
    srv, (host, port) = server_factory(agents, policies, audit_store)

    # Fire a few requests, then stop immediately
    req = InterceptRequest(
        agent_id=str(active_agent.agent_id),
        domain="api.openai.com",
        method="GET",
        path="/",
    )
    for _ in range(5):
        try:
            send_request(host, port, req, timeout=1.0)
        except (ConnectionError, OSError):
            pass  # Some may fail during shutdown, that's fine

    srv.stop()
    # If we get here without exception, shutdown was graceful


def test_requests_processed_counter(
    server_factory, audit_store, active_agent, allow_openai_policy
):
    """Counter matches actual request count."""
    agents, policies = _build_registries(active_agent, allow_openai_policy)
    srv, (host, port) = server_factory(agents, policies, audit_store)

    n = 10
    req = InterceptRequest(
        agent_id=str(active_agent.agent_id),
        domain="api.openai.com",
        method="GET",
        path="/",
    )
    for _ in range(n):
        send_request(host, port, req)

    # Small delay to let all handler threads finish incrementing
    time.sleep(0.2)
    assert srv.requests_processed == n
