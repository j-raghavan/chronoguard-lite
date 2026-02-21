"""Abstract base for audit stores.

Both NaiveAuditStore and ColumnarAuditStore implement this interface.
The point: swap implementations without touching calling code, then
benchmark to show the columnar layout wins on range queries.

Mapped from full ChronoGuard: infrastructure/persistence/audit_repository.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.types import AgentId, DomainName


class AuditStoreBase(ABC):
    """Interface that both naive and columnar stores implement."""

    @abstractmethod
    def append(self, entry: AuditEntry) -> None:
        """Add an entry to the store."""
        ...

    @abstractmethod
    def query_time_range(self, start: float, end: float) -> list[AuditEntry]:
        """Return all entries with start <= timestamp <= end."""
        ...

    @abstractmethod
    def query_by_agent(self, agent_id: AgentId) -> list[AuditEntry]:
        """Return all entries for a given agent."""
        ...

    @abstractmethod
    def query_by_domain(self, domain: DomainName) -> list[AuditEntry]:
        """Return all entries for a given domain."""
        ...

    @abstractmethod
    def query_by_decision(self, decision: AccessDecision) -> list[AuditEntry]:
        """Return all entries with a given decision."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total number of entries."""
        ...

    @abstractmethod
    def memory_usage_bytes(self) -> int:
        """Approximate memory consumption of this store."""
        ...
