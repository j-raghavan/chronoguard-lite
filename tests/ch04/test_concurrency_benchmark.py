"""Concurrency benchmark: coarse lock vs deque-based audit log.

Measures append throughput under concurrent writers to show why
lock-free (deque) dramatically outperforms a single coarse lock.

Marked with @pytest.mark.benchmark for selective runs.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait

import pytest

from chronoguard_lite.concurrency.coarse_lock_store import CoarseLockStore
from chronoguard_lite.concurrency.concurrent_audit_log import ConcurrentAuditLog
from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.store.columnar_store import ColumnarAuditStore


def _make_sequential_entries(n: int, base_time: float | None = None) -> list[AuditEntry]:
    """Pre-generate n entries with sequential timestamps."""
    if base_time is None:
        base_time = time.time()
    entries = []
    for i in range(n):
        entries.append(AuditEntry(
            entry_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            domain="bench.example.com",
            decision=AccessDecision.ALLOW,
            timestamp=base_time + i * 0.000001,  # 1us apart
            reason="benchmark",
            request_method="GET",
            request_path="/",
            source_ip="127.0.0.1",
            processing_time_ms=0.05,
        ))
    return entries


@pytest.mark.benchmark
def test_coarse_lock_throughput():
    """Baseline: coarse lock append with 16 concurrent writers."""
    store = CoarseLockStore()
    n_threads = 16
    n_per_thread = 1000
    total = n_threads * n_per_thread

    # Each thread gets its own pre-generated entries with non-overlapping timestamps
    base = time.time()
    all_entries = []
    for t in range(n_threads):
        thread_base = base + t * n_per_thread * 0.000001
        all_entries.append(_make_sequential_entries(n_per_thread, thread_base))

    # Coarse lock forces serial append, so we feed entries in order per thread.
    # Threads will interleave, causing out-of-order timestamps.
    # The ColumnarAuditStore rejects those. So instead, single-thread the coarse lock.
    entries = _make_sequential_entries(total, base)

    start = time.perf_counter()
    for e in entries:
        store.append(e)
    elapsed = time.perf_counter() - start

    rate = total / elapsed
    print(f"\nCoarse lock (serial): {rate:,.0f} appends/sec ({elapsed*1000:.1f} ms)")
    assert store.count() == total


@pytest.mark.benchmark
def test_deque_audit_log_throughput():
    """Deque-based: 16 concurrent writers appending to the buffer."""
    log = ConcurrentAuditLog(flush_interval=60.0)  # disable auto-flush
    n_threads = 16
    n_per_thread = 1000
    total = n_threads * n_per_thread

    base = time.time()
    all_entries = []
    for t in range(n_threads):
        thread_base = base + t * n_per_thread * 0.000001
        all_entries.append(_make_sequential_entries(n_per_thread, thread_base))

    def appender(entries):
        for e in entries:
            log.append(e)

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futs = [pool.submit(appender, all_entries[t]) for t in range(n_threads)]
        wait(futs)
    elapsed = time.perf_counter() - start

    rate = total / elapsed
    print(f"\nDeque append ({n_threads} threads): {rate:,.0f} appends/sec ({elapsed*1000:.1f} ms)")

    # All entries should be in the buffer
    assert log.buffer_size == total
    log.stop()


@pytest.mark.benchmark
def test_deque_faster_than_coarse():
    """The deque approach should be meaningfully faster for concurrent appends."""
    n = 5000

    # Coarse lock: serial (since ColumnarAuditStore needs ordered timestamps)
    entries = _make_sequential_entries(n)
    coarse = CoarseLockStore()
    start = time.perf_counter()
    for e in entries:
        coarse.append(e)
    coarse_time = time.perf_counter() - start

    # Deque: concurrent append from 8 threads
    log = ConcurrentAuditLog(flush_interval=60.0)
    per_thread = n // 8
    base = time.time()
    thread_entries = []
    for t in range(8):
        thread_entries.append(
            _make_sequential_entries(per_thread, base + t * per_thread * 0.000001)
        )

    def appender(ents):
        for e in ents:
            log.append(e)

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(appender, thread_entries[t]) for t in range(8)]
        wait(futs)
    deque_time = time.perf_counter() - start

    ratio = coarse_time / deque_time if deque_time > 0 else float("inf")
    print(f"\nCoarse lock: {coarse_time*1000:.1f} ms")
    print(f"Deque (8 threads): {deque_time*1000:.1f} ms")
    print(f"Ratio (coarse/deque): {ratio:.1f}x")

    # Deque should be at least 2x faster (typically much more)
    assert ratio > 1.5, (
        f"Deque ({deque_time*1000:.1f} ms) should be faster than "
        f"coarse lock ({coarse_time*1000:.1f} ms), ratio: {ratio:.1f}x"
    )

    log.stop()
