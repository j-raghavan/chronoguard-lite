"""Thread-safe data structures for concurrent access.

Chapter 4 builds three levels of concurrency control:
  - ReadWriteLock: multiple readers OR one writer
  - StripedMap: hash-partitioned locking to reduce contention
  - ConcurrentPolicyCache: striped policy + agent-policy maps
  - ConcurrentAuditLog: deque-based lock-free append with background flush
  - CoarseLockStore: single-lock wrapper for benchmarking comparison
"""
from chronoguard_lite.concurrency.rwlock import ReadWriteLock
from chronoguard_lite.concurrency.striped_map import StripedMap
from chronoguard_lite.concurrency.concurrent_policy_cache import ConcurrentPolicyCache
from chronoguard_lite.concurrency.concurrent_audit_log import ConcurrentAuditLog
from chronoguard_lite.concurrency.coarse_lock_store import CoarseLockStore

__all__ = [
    "ReadWriteLock",
    "StripedMap",
    "ConcurrentPolicyCache",
    "ConcurrentAuditLog",
    "CoarseLockStore",
]
