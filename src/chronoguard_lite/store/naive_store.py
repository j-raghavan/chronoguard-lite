"""Naive audit store: a plain list of AuditEntry objects.

This is intentionally slow for range queries. The point is to measure
why scanning a list of heap-allocated objects defeats the CPU cache:
each AuditEntry is a separate Python object allocated wherever pymalloc
found space, so iterating the list chases pointers all over the heap.

Implementation: all queries are linear scans, O(n) for everything.

Mapped from full ChronoGuard: the "before" version of the audit
repository, roughly equivalent to SELECT * FROM audit WHERE ...
but without an index.
"""
from __future__ import annotations

import sys

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.types import AgentId, DomainName
from chronoguard_lite.store.base import AuditStoreBase


class NaiveAuditStore(AuditStoreBase):
    """Store entries in a list[AuditEntry]. Simple, correct, cache-hostile.

    Every query is a full linear scan:
      query_time_range:  iterate all, compare timestamp
      query_by_agent:    iterate all, compare agent_id
      query_by_domain:   iterate all, compare domain string
      query_by_decision: iterate all, compare decision enum

    memory_usage_bytes: counts the list shell, each entry shell, and
    every field value on each entry. This gives a fair comparison
    with the columnar store, which also counts its array contents.
    """

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def query_time_range(self, start: float, end: float) -> list[AuditEntry]:
        return [e for e in self._entries if start <= e.timestamp <= end]

    def query_by_agent(self, agent_id: AgentId) -> list[AuditEntry]:
        return [e for e in self._entries if e.agent_id == agent_id]

    def query_by_domain(self, domain: DomainName) -> list[AuditEntry]:
        return [e for e in self._entries if e.domain == domain]

    def query_by_decision(self, decision: AccessDecision) -> list[AuditEntry]:
        return [e for e in self._entries if e.decision == decision]

    def count(self) -> int:
        return len(self._entries)

    # Fields on AuditEntry that hold Python objects worth counting.
    # We skip timestamp (float) and processing_time_ms (float) and
    # decision (enum singleton) because those are tiny or shared,
    # but we do count them for fairness with the columnar store.
    _ENTRY_FIELDS = (
        "entry_id", "agent_id", "domain", "decision", "timestamp",
        "reason", "policy_id", "rule_id", "request_method",
        "request_path", "source_ip", "processing_time_ms",
    )

    def memory_usage_bytes(self) -> int:
        """Count list shell + entry shells + every field value.

        This gives the full cost of the object graph so we can
        compare apples-to-apples with the columnar store.
        """
        total = sys.getsizeof(self._entries)
        for entry in self._entries:
            total += sys.getsizeof(entry)
            for field in self._ENTRY_FIELDS:
                val = getattr(entry, field)
                if val is not None:
                    total += sys.getsizeof(val)
        return total
