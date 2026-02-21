"""GIL benchmark: measure throughput vs thread count.

The key assertion: throughput at 16 threads should NOT be meaningfully
higher than at 4 threads. The GIL serializes the CPU-bound evaluation
work, so adding threads past the point where I/O wait is saturated
doesn't help and eventually hurts (context-switch overhead).

We deliberately add CPU work in the evaluator path (policy evaluation,
JSON serialization, AuditEntry creation, UUID parsing) to make the
GIL contention visible even in a test environment.

These are slow tests (~10s each) so they're marked with pytest.mark.slow.
Run with: pytest -m benchmark tests/ch03/test_gil_benchmark.py
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pytest

from chronoguard_lite.domain.agent import Agent, AgentStatus
from chronoguard_lite.domain.policy import Policy, PolicyRule, PolicyStatus
from chronoguard_lite.interceptor.protocol import InterceptRequest
from chronoguard_lite.interceptor.threaded import ThreadedInterceptor
from chronoguard_lite.store.columnar_store import ColumnarAuditStore

from tests.ch03.conftest import send_request


# ---------------------------------------------------------------------------
# Fixtures: heavier setup than unit tests -- multiple policies with rules
# ---------------------------------------------------------------------------

def _build_heavy_setup():
    """Create an agent with 10 policies, each with 5 rules.

    This makes the evaluator do real work per request: sort 10 policies,
    iterate rules, match domain patterns. Enough to hold the GIL for
    a measurable amount of time per request.
    """
    now = datetime.now(timezone.utc)
    agent = Agent(
        agent_id=uuid.uuid4(),
        name="benchmark-agent",
        status=AgentStatus.ACTIVE,
        policy_ids=[],
        created_at=now,
        updated_at=now,
    )
    policies = {}
    for i in range(10):
        p = Policy.create(name=f"policy-{i}", priority=i * 10)
        for j in range(5):
            p.add_rule(PolicyRule.allow(f"svc-{i}-{j}.example.com", priority=j))
        # The last policy has the domain we'll actually request
        if i == 9:
            p.add_rule(PolicyRule.allow("target.benchmark.com", priority=99))
        p.status = PolicyStatus.ACTIVE
        agent.policy_ids.append(p.policy_id)
        policies[str(p.policy_id)] = p

    agents = {str(agent.agent_id): agent}
    return agents, policies, agent


def _measure_throughput(
    max_workers: int,
    n_requests: int = 200,
    n_clients: int = 50,
) -> float:
    """Start an interceptor with max_workers threads, fire n_requests
    concurrently, return requests/sec.
    """
    agents, policies, agent = _build_heavy_setup()
    store = ColumnarAuditStore()
    srv = ThreadedInterceptor(
        host="127.0.0.1",
        port=0,
        max_workers=max_workers,
        agents=agents,
        policies=policies,
        audit_store=store,
    )
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    srv.wait_ready()
    time.sleep(0.05)
    host, port = srv.address

    req = InterceptRequest(
        agent_id=str(agent.agent_id),
        domain="target.benchmark.com",
        method="POST",
        path="/v1/heavy",
        source_ip="10.0.0.99",
    )

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_clients) as pool:
        futs = [pool.submit(send_request, host, port, req) for _ in range(n_requests)]
        for f in as_completed(futs):
            f.result()  # raise if any failed
    elapsed = time.perf_counter() - start

    srv.stop()
    return n_requests / elapsed


@pytest.mark.benchmark
def test_throughput_scaling():
    """Throughput plateaus as we add threads -- the GIL in action.

    We measure at 1, 4, and 16 worker threads. The key assertion:
    going from 4 to 16 threads should give less than 1.5x improvement.
    On a GIL-bound workload, it's typically less than 1.1x.
    """
    tp_1 = _measure_throughput(max_workers=1, n_requests=100, n_clients=20)
    tp_4 = _measure_throughput(max_workers=4, n_requests=200, n_clients=50)
    tp_16 = _measure_throughput(max_workers=16, n_requests=200, n_clients=50)

    print(f"\n--- GIL Benchmark ---")
    print(f"  1 thread:   {tp_1:.0f} req/s")
    print(f"  4 threads:  {tp_4:.0f} req/s")
    print(f" 16 threads:  {tp_16:.0f} req/s")
    print(f"  Ratio 16/4: {tp_16 / tp_4:.2f}x")

    # The plateau: 16 threads should NOT be much faster than 4
    # Allow up to 1.5x to account for I/O overlap, but the real
    # number is typically 1.0-1.2x on a GIL-bound workload.
    assert tp_16 / tp_4 < 1.5, (
        f"Expected GIL plateau: 16 threads gave {tp_16/tp_4:.2f}x over 4 threads. "
        f"If this ratio is consistently above 1.5, the workload may not be "
        f"CPU-bound enough to demonstrate the GIL."
    )

    # Sanity: 4 threads should be at least a bit faster than 1 thread
    # (because some I/O overlap does help, even with the GIL)
    assert tp_4 > tp_1 * 0.8, (
        f"4 threads ({tp_4:.0f}) should not be dramatically slower than "
        f"1 thread ({tp_1:.0f})"
    )


@pytest.mark.benchmark
def test_all_requests_correct():
    """Sanity: even under concurrent load, every response is correct."""
    agents, policies, agent = _build_heavy_setup()
    store = ColumnarAuditStore()
    srv = ThreadedInterceptor(
        host="127.0.0.1",
        port=0,
        max_workers=8,
        agents=agents,
        policies=policies,
        audit_store=store,
    )
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    srv.wait_ready()
    time.sleep(0.05)
    host, port = srv.address

    req = InterceptRequest(
        agent_id=str(agent.agent_id),
        domain="target.benchmark.com",
        method="GET",
        path="/check",
    )

    n = 100
    results = []
    with ThreadPoolExecutor(max_workers=30) as pool:
        futs = [pool.submit(send_request, host, port, req) for _ in range(n)]
        for f in as_completed(futs):
            results.append(f.result())

    srv.stop()

    assert len(results) == n
    assert all(r.decision == "ALLOW" for r in results)
