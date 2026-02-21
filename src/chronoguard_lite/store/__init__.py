"""Audit store implementations: naive (list-based) and columnar (array-based).

Chapter 2 builds both stores to demonstrate the performance impact of
memory layout on range queries. The naive store is the baseline; the
columnar store is the optimized version.
"""
from chronoguard_lite.store.base import AuditStoreBase
from chronoguard_lite.store.columnar_store import ColumnarAuditStore
from chronoguard_lite.store.naive_store import NaiveAuditStore
from chronoguard_lite.store.queries import TimeRange

__all__ = [
    "AuditStoreBase",
    "ColumnarAuditStore",
    "NaiveAuditStore",
    "TimeRange",
]
