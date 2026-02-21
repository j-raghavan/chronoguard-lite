"""Striped hash map: distribute lock contention across N stripes.

Instead of one lock for the entire dict, we use N read-write locks.
Each key maps to a stripe via: stripe_index = hash(key) & (N - 1).
With 16 stripes and 16 threads, contention drops roughly 16x vs
a single lock, because threads only block each other when they
happen to hit the same stripe.

The power-of-two requirement on num_stripes lets us use a bitmask
instead of modulo for stripe selection. hash(key) & mask is faster
than hash(key) % num_stripes, and it matters when this is on the
hot path for every policy lookup.

Mapped from full ChronoGuard: the Redis-backed policy cache
partitions keys across Redis cluster slots. Here we partition
across in-memory dict stripes protected by RWLocks.
"""
from __future__ import annotations

from typing import TypeVar

from chronoguard_lite.concurrency.rwlock import ReadWriteLock

K = TypeVar("K")
V = TypeVar("V")


class StripedMap:
    """Thread-safe hash map with striped read-write locks.

    Args:
        num_stripes: Number of lock stripes (default 16, must be power of 2).
    """

    def __init__(self, num_stripes: int = 16) -> None:
        if num_stripes <= 0 or (num_stripes & (num_stripes - 1)) != 0:
            raise ValueError("num_stripes must be a positive power of 2")
        self._num_stripes = num_stripes
        self._stripes: list[dict] = [{} for _ in range(num_stripes)]
        self._locks: list[ReadWriteLock] = [
            ReadWriteLock() for _ in range(num_stripes)
        ]
        self._mask = num_stripes - 1

    def get(self, key: K) -> V | None:
        """Read: acquires read lock on the key's stripe only."""
        idx = self._stripe_index(key)
        with self._locks[idx].read():
            return self._stripes[idx].get(key)

    def put(self, key: K, value: V) -> None:
        """Write: acquires write lock on the key's stripe only."""
        idx = self._stripe_index(key)
        with self._locks[idx].write():
            self._stripes[idx][key] = value

    def delete(self, key: K) -> bool:
        """Delete: acquires write lock. Returns True if key existed."""
        idx = self._stripe_index(key)
        with self._locks[idx].write():
            if key in self._stripes[idx]:
                del self._stripes[idx][key]
                return True
            return False

    def contains(self, key: K) -> bool:
        """Check existence: acquires read lock."""
        idx = self._stripe_index(key)
        with self._locks[idx].read():
            return key in self._stripes[idx]

    def size(self) -> int:
        """Total entries across all stripes.

        Acquires each read lock sequentially. This is NOT a point-in-time
        snapshot: concurrent writes during the scan can make the total
        approximate. Good enough for monitoring, not for invariants.
        """
        total = 0
        for i in range(self._num_stripes):
            with self._locks[i].read():
                total += len(self._stripes[i])
        return total

    def keys(self) -> list[K]:
        """Snapshot of all keys. Same caveat as size(): not atomic."""
        result: list[K] = []
        for i in range(self._num_stripes):
            with self._locks[i].read():
                result.extend(self._stripes[i].keys())
        return result

    def values(self) -> list[V]:
        """Snapshot of all values. Same caveat as size(): not atomic."""
        result: list[V] = []
        for i in range(self._num_stripes):
            with self._locks[i].read():
                result.extend(self._stripes[i].values())
        return result

    def update(self, key: K, func, default=None):
        """Atomic read-modify-write: acquires write lock, applies func.

        func receives the current value (or default if key is absent)
        and returns the new value. The entire operation holds the
        write lock on the key's stripe, so no other thread can
        interleave between the read and write.
        """
        idx = self._stripe_index(key)
        with self._locks[idx].write():
            current = self._stripes[idx].get(key, default)
            new_val = func(current)
            self._stripes[idx][key] = new_val
            return new_val

    def _stripe_index(self, key: K) -> int:
        return hash(key) & self._mask
