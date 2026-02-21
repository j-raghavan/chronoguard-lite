"""Coarse-grained lock wrapper around ColumnarAuditStore.

One big threading.Lock around every operation. Simple and correct,
but contention-heavy under concurrent writes because every thread
blocks on the same lock regardless of what they're doing.

This exists purely as a benchmark baseline. The reader compares:
  1. CoarseLockStore (this file): one lock, maximum contention
  2. ConcurrentAuditLog (deque + flush): effectively lock-free append
  3. StripedMap: striped locking, contention drops ~N-fold

The benchmark in test_concurrency_benchmark.py makes the tradeoff visible.
"""
from __future__ import annotations

import threading

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.store.columnar_store import ColumnarAuditStore


class CoarseLockStore:
    """ColumnarAuditStore wrapped in a single coarse lock.

    Every method acquires the same lock. Under 16 concurrent writers,
    throughput is limited to ~1/16 of the lock-free alternative because
    threads serialize on a single contention point.
    """

    def __init__(self, store: ColumnarAuditStore | None = None) -> None:
        self._store = store or ColumnarAuditStore()
        self._lock = threading.Lock()

    def append(self, entry: AuditEntry) -> None:
        with self._lock:
            self._store.append(entry)

    def count(self) -> int:
        with self._lock:
            return self._store.count()

    def query_time_range(self, start: float, end: float) -> list[AuditEntry]:
        with self._lock:
            return self._store.query_time_range(start, end)

    @property
    def store(self) -> ColumnarAuditStore:
        return self._store
