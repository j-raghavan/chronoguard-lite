"""Tests for AsyncInterceptor: the asyncio TCP server."""
from __future__ import annotations

import asyncio
import time

import pytest

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.interceptor.async_interceptor import AsyncInterceptor
from chronoguard_lite.interceptor.protocol import InterceptRequest, InterceptResponse

from tests.ch05.conftest import async_send_request, start_async_server


def _build_agents_and_policies(active_agent, allow_openai_policy, deny_malware_policy):
    """Convert fixtures into the dicts the interceptor expects."""
    agents = {str(active_agent.agent_id): active_agent}
    policies = {
        str(allow_openai_policy.policy_id): allow_openai_policy,
        str(deny_malware_policy.policy_id): deny_malware_policy,
    }
    return agents, policies


@pytest.mark.asyncio
async def test_single_request(
    active_agent, allow_openai_policy, deny_malware_policy, audit_store
):
    """A single request through the async interceptor returns ALLOW."""
    agents, policies = _build_agents_and_policies(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv = await start_async_server(agents, policies, audit_store)
    try:
        host, port = srv.address
        req = InterceptRequest(
            agent_id=str(active_agent.agent_id),
            domain="api.openai.com",
            method="GET",
            path="/v1/models",
        )
        resp = await async_send_request(host, port, req)
        assert resp.decision == "ALLOW"
        assert "allow-openai" in resp.reason
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_deny_request(
    active_agent, allow_openai_policy, deny_malware_policy, audit_store
):
    """A request to a denied domain returns DENY."""
    agents, policies = _build_agents_and_policies(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv = await start_async_server(agents, policies, audit_store)
    try:
        host, port = srv.address
        req = InterceptRequest(
            agent_id=str(active_agent.agent_id),
            domain="malware.example.com",
            method="GET",
            path="/payload",
        )
        resp = await async_send_request(host, port, req)
        assert resp.decision == "DENY"
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_unknown_agent(
    active_agent, allow_openai_policy, deny_malware_policy, audit_store
):
    """A request from an unknown agent returns DENY."""
    agents, policies = _build_agents_and_policies(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv = await start_async_server(agents, policies, audit_store)
    try:
        host, port = srv.address
        req = InterceptRequest(
            agent_id="00000000-0000-0000-0000-000000000000",
            domain="api.openai.com",
            method="GET",
            path="/v1/models",
        )
        resp = await async_send_request(host, port, req)
        assert resp.decision == "DENY"
        assert "Unknown agent" in resp.reason
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_concurrent_100(
    active_agent, allow_openai_policy, deny_malware_policy, audit_store
):
    """100 concurrent requests all get correct responses."""
    agents, policies = _build_agents_and_policies(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv = await start_async_server(agents, policies, audit_store)
    try:
        host, port = srv.address
        req = InterceptRequest(
            agent_id=str(active_agent.agent_id),
            domain="api.openai.com",
            method="GET",
            path="/v1/models",
        )

        async def send_one():
            return await async_send_request(host, port, req)

        tasks = [asyncio.create_task(send_one()) for _ in range(100)]
        results = await asyncio.gather(*tasks)

        assert all(r.decision == "ALLOW" for r in results)
        assert len(results) == 100
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_audit_entries_flushed(
    active_agent, allow_openai_policy, deny_malware_policy, audit_store
):
    """Audit entries from async interceptor end up in the columnar store."""
    agents, policies = _build_agents_and_policies(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv = await start_async_server(agents, policies, audit_store)
    try:
        host, port = srv.address
        req = InterceptRequest(
            agent_id=str(active_agent.agent_id),
            domain="api.openai.com",
            method="GET",
            path="/v1/models",
        )
        # Send 10 requests
        for _ in range(10):
            await async_send_request(host, port, req)
    finally:
        await srv.stop()

    # After stop(), the queue should be fully drained
    assert audit_store.count() == 10


@pytest.mark.asyncio
async def test_requests_processed_counter(
    active_agent, allow_openai_policy, deny_malware_policy, audit_store
):
    """The requests_processed counter increments correctly."""
    agents, policies = _build_agents_and_policies(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    srv = await start_async_server(agents, policies, audit_store)
    try:
        host, port = srv.address
        req = InterceptRequest(
            agent_id=str(active_agent.agent_id),
            domain="api.openai.com",
            method="GET",
            path="/v1/models",
        )
        for _ in range(5):
            await async_send_request(host, port, req)

        # Give the event loop a moment to update the counter
        await asyncio.sleep(0.05)
        assert srv.requests_processed == 5
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_graceful_shutdown_drains_queue(
    active_agent, allow_openai_policy, deny_malware_policy, audit_store
):
    """stop() drains the audit queue before returning."""
    agents, policies = _build_agents_and_policies(
        active_agent, allow_openai_policy, deny_malware_policy
    )
    # Small queue to make backpressure observable
    srv = await start_async_server(
        agents, policies, audit_store, queue_maxsize=100
    )
    try:
        host, port = srv.address
        req = InterceptRequest(
            agent_id=str(active_agent.agent_id),
            domain="api.openai.com",
            method="GET",
            path="/v1/models",
        )
        # Send 50 requests quickly
        tasks = [
            asyncio.create_task(async_send_request(host, port, req))
            for _ in range(50)
        ]
        await asyncio.gather(*tasks)
    finally:
        await srv.stop()

    # After stop, queue must be empty and all entries flushed
    assert srv.queue_size == 0
    assert audit_store.count() == 50
