"""Read-write lock: multiple concurrent readers OR one exclusive writer.

Implementation: threading.Condition with reader count tracking.
Writer preference: once a writer is waiting, new readers block.
This prevents writer starvation under heavy read load.

Usage:
    lock = ReadWriteLock()

    with lock.read():
        data = shared_dict[key]   # Multiple threads here concurrently

    with lock.write():
        shared_dict[key] = value  # Exclusive access

Mapped from full ChronoGuard: the Redis-backed cache uses optimistic
reads with CAS for writes. Here we build the primitive from scratch
so the reader understands what Redis is abstracting away.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


class ReadWriteLock:
    """Fair read-write lock with writer preference.

    Writer preference means: once a writer is waiting, new readers
    block until the writer finishes. Without this, a steady stream
    of readers can starve writers indefinitely. The cost is slightly
    lower read throughput under contention, but writes always make
    progress.
    """

    def __init__(self) -> None:
        self._readers: int = 0
        self._writers_waiting: int = 0
        self._writer_active: bool = False
        self._cond = threading.Condition(threading.Lock())

    @contextmanager
    def read(self) -> Iterator[None]:
        """Acquire read lock. Blocks if a writer is active or waiting."""
        with self._cond:
            while self._writer_active or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._cond:
                self._readers -= 1
                if self._readers == 0:
                    self._cond.notify_all()

    @contextmanager
    def write(self) -> Iterator[None]:
        """Acquire write lock. Blocks if readers or another writer active."""
        with self._cond:
            self._writers_waiting += 1
            while self._writer_active or self._readers > 0:
                self._cond.wait()
            self._writers_waiting -= 1
            self._writer_active = True
        try:
            yield
        finally:
            with self._cond:
                self._writer_active = False
                self._cond.notify_all()
