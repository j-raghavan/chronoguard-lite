"""Lock-free append-only audit log using collections.deque.

Why deque? CPython's deque.append() is implemented in C and holds the
GIL for a very short critical section (just pointer manipulation on the
doubly-linked block list). In practice this means multiple threads can
append without explicit locking. It's not truly "lock-free" in the
academic sense (it still holds the GIL), but it's the closest you get
in CPython without dropping into C extensions.

A background thread periodically flushes the deque buffer into the
ColumnarAuditStore. This decouples the hot path (append) from the
slower path (columnar store insertion with array.array resizes and
encoding).

Mapped from full ChronoGuard: the production system uses a Redis
Streams-backed audit pipeline with consumer groups. Here we replace
that with an in-memory deque + flush thread.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.store.columnar_store import ColumnarAuditStore


class ConcurrentAuditLog:
    """Append-optimized audit log with background flush to columnar store.

    Args:
        store: The backing ColumnarAuditStore (optional, created if None).
        flush_interval: Seconds between background flushes (default 0.1).
        max_buffer_size: Advisory limit (not currently enforced in append).
    """

    def __init__(
        self,
        store: ColumnarAuditStore | None = None,
        flush_interval: float = 0.1,
        max_buffer_size: int = 10_000,
    ) -> None:
        self._store = store or ColumnarAuditStore()
        self._buffer: deque[AuditEntry] = deque()
        self._flush_interval = flush_interval
        self._max_buffer_size = max_buffer_size
        self._running = False
        self._flush_thread: threading.Thread | None = None
        self._flush_count = 0
        self._lock = threading.Lock()  # protects _flush_count only

    def append(self, entry: AuditEntry) -> None:
        """Append an audit entry to the buffer.

        This is the hot path. deque.append() is O(1) and effectively
        lock-free under CPython (the GIL protects the internal pointer
        manipulation, but no Python-level lock is acquired).
        """
        self._buffer.append(entry)

    def start(self) -> None:
        """Start the background flush thread."""
        if self._running:
            return
        self._running = True
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="audit-flush"
        )
        self._flush_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the flush thread and drain any remaining buffer."""
        self._running = False
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=timeout)
            self._flush_thread = None
        # Final flush to catch anything left in the buffer
        self._flush_buffer()

    def _flush_loop(self) -> None:
        """Background loop: sleep, flush, repeat."""
        while self._running:
            time.sleep(self._flush_interval)
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Drain the buffer into the columnar store.

        We pop from the left (FIFO order) one entry at a time.
        deque.popleft() is O(1) and safe to call while other threads
        are calling append() on the right side.

        The columnar store's append() enforces chronological ordering.
        Entries usually arrive in order because time.time() usually
        increases, but it is NOT monotonic: NTP adjustments and clock
        sync can push it backward. If an entry arrives out of order,
        the store raises ValueError and we drop that entry. This is a
        teaching simplification; a production system would re-sort or
        use time.monotonic() for ordering.
        """
        flushed = 0
        while self._buffer:
            try:
                entry = self._buffer.popleft()
                self._store.append(entry)
                flushed += 1
            except ValueError:
                # Out-of-order timestamp: columnar store rejects it.
                # This version drops the entry. A production system
                # would re-sort or buffer until ordering is restored.
                pass
            except IndexError:
                # Buffer emptied between the while-check and popleft.
                # With a single consumer thread this should not fire,
                # but it's cheap insurance.
                break

        if flushed > 0:
            with self._lock:
                self._flush_count += flushed

    @property
    def buffer_size(self) -> int:
        """Current number of entries waiting to be flushed."""
        return len(self._buffer)

    @property
    def flush_count(self) -> int:
        """Total entries flushed to the backing store so far."""
        with self._lock:
            return self._flush_count

    @property
    def store(self) -> ColumnarAuditStore:
        """Access the backing columnar store."""
        return self._store

    @property
    def total_entries(self) -> int:
        """Total entries: flushed + still in buffer."""
        return self._store.count() + len(self._buffer)
