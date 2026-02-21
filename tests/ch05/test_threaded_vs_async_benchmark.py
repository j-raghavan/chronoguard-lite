"""Benchmark: threaded interceptor vs async interceptor.

Measures throughput (requests/second) under concurrent client load.
The async version should be significantly faster because it avoids
GIL contention and OS thread scheduling overhead.

The benchmark fires N concurrent clients, each sending a burst of
sequential requests. We measure wall-clock time and compute req/s.

These numbers are from one run on a single machine; your results
will vary with core count, OS scheduler, and background load.
"""
from __future__ import annotations

import asyncio
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from chronoguard_lite.domain.agent import Agent, AgentStatus
from chronoguard_lite.domain.policy import Policy, PolicyRule, PolicyStatus
from chronoguard_lite.interceptor.async_interceptor import AsyncInterceptor
from chronoguard_lite.interceptor.protocol import (
    InterceptRequest,
    InterceptResponse,
    read_message,
    write_message,
)
from chronoguard_lite.interceptor.threaded import ThreadedInterceptor
from chronoguard_lite.store.columnar_store import ColumnarAuditStore
from tests.ch05.conftest import async_send_request, start_async_server


def _build_setup():
    """Create a realistic agent + policy setup for benchmarking."""
    policies = []
    for i in range(10):
        p = Policy.create(name=f"policy-{i}", priority=i * 10)
        for j in range(5):
            p.add_rule(PolicyRule.allow(f"domain-{i}-{j}.example.com", priority=j))
        p.status = PolicyStatus.ACTIVE
        policies.append(p)

    now = datetime.now(timezone.utc)
    agent = Agent(
        agent_id=uuid.uuid4(),
        name="bench-agent",
        status=AgentStatus.ACTIVE,
        policy_ids=[p.policy_id for p in policies],
        created_at=now,
        updated_at=now,
    )

    agents_dict = {str(agent.agent_id): agent}
    policies_dict = {str(p.policy_id): p for p in policies}
    return agent, agents_dict, policies_dict


def _sync_send(host, port, req_bytes):
    """Send one request via blocking socket, return response bytes."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10.0)
    try:
        s.connect((host, port))
        s.sendall(req_bytes)
        return read_message(s)
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Threaded benchmark
# ---------------------------------------------------------------------------

def _measure_threaded(n_clients, requests_per_client):
    agent, agents_dict, policies_dict = _build_setup()
    store = ColumnarAuditStore()

    srv = ThreadedInterceptor(
        host="127.0.0.1",
        port=0,
        max_workers=16,
        agents=agents_dict,
        policies=policies_dict,
        audit_store=store,
    )
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    srv.wait_ready(timeout=5.0)
    time.sleep(0.05)
    host, port = srv.address

    req = InterceptRequest(
        agent_id=str(agent.agent_id),
        domain="api.openai.com",
        method="GET",
        path="/v1/models",
    )
    req_bytes = req.to_bytes()

    def client_burst():
        for _ in range(requests_per_client):
            _sync_send(host, port, req_bytes)

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_clients) as pool:
        futs = [pool.submit(client_burst) for _ in range(n_clients)]
        for f in futs:
            f.result(timeout=30)
    elapsed = time.perf_counter() - start

    srv.stop()
    total = n_clients * requests_per_client
    return total / elapsed


# ---------------------------------------------------------------------------
# Async benchmark
# ---------------------------------------------------------------------------

async def _measure_async(n_clients, requests_per_client):
    agent, agents_dict, policies_dict = _build_setup()
    store = ColumnarAuditStore()

    srv = await start_async_server(agents_dict, policies_dict, store)
    host, port = srv.address

    req = InterceptRequest(
        agent_id=str(agent.agent_id),
        domain="api.openai.com",
        method="GET",
        path="/v1/models",
    )

    async def client_burst():
        for _ in range(requests_per_client):
            await async_send_request(host, port, req)

    start = time.perf_counter()
    tasks = [asyncio.create_task(client_burst()) for _ in range(n_clients)]
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    await srv.stop()
    total = n_clients * requests_per_client
    return total / elapsed


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.benchmark
def test_threaded_throughput():
    """Baseline: threaded interceptor throughput at 50 concurrent clients."""
    rps = _measure_threaded(n_clients=50, requests_per_client=10)
    print(f"\nThreaded: {rps:.0f} req/s (50 clients x 10 requests)")
    # Sanity: should do at least 500 req/s even in slow environments
    assert rps > 500


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_async_throughput():
    """Async interceptor throughput at 50 concurrent clients."""
    rps = await _measure_async(n_clients=50, requests_per_client=10)
    print(f"\nAsync: {rps:.0f} req/s (50 clients x 10 requests)")
    # Async should do at least 1000 req/s
    assert rps > 1000


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_async_faster_than_threaded():
    """The async interceptor should outperform the threaded version.

    We measure both at 100 clients x 5 requests and compare. The async
    version typically wins by 1.5-3x, but on fast machines with low
    thread overhead the gap can be smaller. We assert > 1.0x (async
    is at least not slower) to avoid flaky failures across environments.
    """
    threaded_rps = _measure_threaded(n_clients=100, requests_per_client=5)
    async_rps = await _measure_async(n_clients=100, requests_per_client=5)
    ratio = async_rps / threaded_rps

    print(f"\n--- Threaded vs Async ---")
    print(f"  Threaded: {threaded_rps:.0f} req/s")
    print(f"  Async:    {async_rps:.0f} req/s")
    print(f"  Ratio:    {ratio:.2f}x")

    # On most machines async wins by 1.5-3x, but on fast hardware with
    # low thread overhead the margin can be slim. We just assert async
    # is not slower; the printed numbers are the real teaching tool.
    assert ratio > 1.0, (
        f"Expected async to be at least as fast: {async_rps:.0f} vs {threaded_rps:.0f} "
        f"(ratio {ratio:.2f}x)"
    )
