"""Columnar audit store: struct-of-arrays layout for cache-friendly access.

Instead of storing N AuditEntry objects (each a separate heap allocation,
scattered wherever pymalloc found space), we decompose each entry into
separate typed arrays, one per field. Range queries on timestamps scan a
contiguous array('d'), and the CPU prefetcher loves contiguous reads.

Layout:
    timestamps:    array('d')          8 bytes each, contiguous
    agent_ids:     list[bytes]         UUID.bytes, 16 bytes each
    domains:       list[str]           string references (unavoidable)
    decisions:     array('B')          1 byte each (enum .value)
    reasons:       list[str]
    policy_ids:    list[bytes | None]  UUID.bytes or None
    rule_ids:      list[bytes | None]
    entry_ids:     list[bytes]         UUID.bytes
    methods:       array('B')          GET=0, POST=1, PUT=2, DELETE=3
    paths:         list[str]
    source_ips:    list[str]
    latencies:     array('f')          4-byte float, milliseconds

Key optimization: timestamps are stored sorted (we enforce chronological
append order), enabling bisect-based range queries in O(log n + k) where
k is the number of matching entries. Compare that to O(n) for the naive
linear scan.

Mapped from full ChronoGuard: this is the in-memory equivalent of a
TimescaleDB hypertable with a btree index on timestamp.
"""
from __future__ import annotations

import array
import bisect
import sys
import uuid

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.types import AgentId, DomainName
from chronoguard_lite.store.base import AuditStoreBase


class ColumnarAuditStore(AuditStoreBase):
    """Cache-friendly columnar store.

    INVARIANT: entries must be appended in chronological order.
    This lets us use bisect on the timestamps array without sorting.
    Violating the invariant raises ValueError immediately.
    """

    METHOD_ENCODING: dict[str, int] = {
        "GET": 0, "POST": 1, "PUT": 2, "DELETE": 3,
        "PATCH": 4, "HEAD": 5, "OPTIONS": 6,
    }
    METHOD_DECODING: dict[int, str] = {v: k for k, v in METHOD_ENCODING.items()}

    __slots__ = (
        "_timestamps", "_agent_ids", "_domains", "_decisions",
        "_reasons", "_policy_ids", "_rule_ids", "_entry_ids",
        "_methods", "_paths", "_source_ips", "_latencies", "_count",
    )

    def __init__(self) -> None:
        self._timestamps = array.array("d")       # float64, contiguous
        self._agent_ids: list[bytes] = []          # UUID.bytes (16 bytes each)
        self._domains: list[str] = []
        self._decisions = array.array("B")         # uint8 (AccessDecision.value)
        self._reasons: list[str] = []
        self._policy_ids: list[bytes | None] = []  # UUID.bytes or None
        self._rule_ids: list[bytes | None] = []
        self._entry_ids: list[bytes] = []
        self._methods = array.array("B")           # encoded HTTP method
        self._paths: list[str] = []
        self._source_ips: list[str] = []
        self._latencies = array.array("f")         # float32
        self._count: int = 0

    def append(self, entry: AuditEntry) -> None:
        """Decompose AuditEntry into columnar arrays.

        Raises ValueError if entry.timestamp < last appended timestamp.
        We need sorted order for bisect to work.
        """
        ts = entry.timestamp
        if self._count > 0 and ts < self._timestamps[-1]:
            raise ValueError(
                f"Out-of-order append: {ts} < last timestamp "
                f"{self._timestamps[-1]}. Entries must be chronological."
            )

        self._timestamps.append(ts)
        self._agent_ids.append(entry.agent_id.bytes)
        self._domains.append(entry.domain)
        self._decisions.append(entry.decision.value)
        self._reasons.append(entry.reason)
        self._policy_ids.append(
            entry.policy_id.bytes if entry.policy_id is not None else None
        )
        self._rule_ids.append(
            entry.rule_id.bytes if entry.rule_id is not None else None
        )
        self._entry_ids.append(entry.entry_id.bytes)
        self._methods.append(
            self.METHOD_ENCODING.get(entry.request_method, 0)
        )
        self._paths.append(entry.request_path)
        self._source_ips.append(entry.source_ip)
        self._latencies.append(entry.processing_time_ms)
        self._count += 1

    def query_time_range(self, start: float, end: float) -> list[AuditEntry]:
        """Binary search on timestamps, then reconstruct the matching slice.

        O(log n) to find the boundaries, O(k) to reconstruct k entries.
        Compare to O(n) for the naive store's linear scan.
        """
        left = bisect.bisect_left(self._timestamps, start)
        right = bisect.bisect_right(self._timestamps, end)
        return [self._reconstruct_entry(i) for i in range(left, right)]

    def query_by_agent(self, agent_id: AgentId) -> list[AuditEntry]:
        """Linear scan on agent_ids (bytes comparison).

        Still O(n), but comparing 16-byte blobs in a list is faster
        than chasing pointers into scattered AuditEntry objects and
        then into their UUID fields.
        """
        target = agent_id.bytes
        return [
            self._reconstruct_entry(i)
            for i in range(self._count)
            if self._agent_ids[i] == target
        ]

    def query_by_domain(self, domain: DomainName) -> list[AuditEntry]:
        """Linear scan on domains list."""
        return [
            self._reconstruct_entry(i)
            for i in range(self._count)
            if self._domains[i] == domain
        ]

    def query_by_decision(self, decision: AccessDecision) -> list[AuditEntry]:
        """Scan decisions array (single byte comparison).

        The decisions array is contiguous uint8 values, so this
        scan hits the L1 cache nicely.
        """
        val = decision.value
        return [
            self._reconstruct_entry(i)
            for i in range(self._count)
            if self._decisions[i] == val
        ]

    def count(self) -> int:
        return self._count

    def _reconstruct_entry(self, idx: int) -> AuditEntry:
        """Rebuild an AuditEntry from column values at the given index.

        This is the cost of columnar layout: reconstruction requires
        gathering values from 12 separate arrays. Worth it when your
        query only touches a fraction of the total rows (range queries),
        not worth it when you need every row (full table scan + reconstruct).
        """
        pid_bytes = self._policy_ids[idx]
        rid_bytes = self._rule_ids[idx]
        return AuditEntry(
            entry_id=uuid.UUID(bytes=self._entry_ids[idx]),
            agent_id=uuid.UUID(bytes=self._agent_ids[idx]),
            domain=self._domains[idx],
            decision=AccessDecision(self._decisions[idx]),
            timestamp=self._timestamps[idx],
            reason=self._reasons[idx],
            policy_id=uuid.UUID(bytes=pid_bytes) if pid_bytes is not None else None,
            rule_id=uuid.UUID(bytes=rid_bytes) if rid_bytes is not None else None,
            request_method=self.METHOD_DECODING.get(self._methods[idx], "GET"),
            request_path=self._paths[idx],
            source_ip=self._source_ips[idx],
            processing_time_ms=self._latencies[idx],
        )

    def memory_usage_bytes(self) -> int:
        """Approximate memory consumption.

        For array.array: buffer size = len * itemsize
        For lists of strings/bytes: sys.getsizeof(list) + sum of element sizes
        """
        total = 0

        # Typed arrays: contiguous buffers
        for arr in (self._timestamps, self._decisions, self._methods, self._latencies):
            total += sys.getsizeof(arr)

        # Lists of bytes/strings: list shell + elements
        for lst in (
            self._agent_ids, self._domains, self._reasons,
            self._policy_ids, self._rule_ids, self._entry_ids,
            self._paths, self._source_ips,
        ):
            total += sys.getsizeof(lst)
            for item in lst:
                if item is not None:
                    total += sys.getsizeof(item)

        return total
