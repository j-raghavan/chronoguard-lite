"""AuditSearchEngine: query parser + inverted index for audit log search.

Provides a simple query language for searching audit entries:

    "domain:openai AND decision:deny"
    "agent_id:550e8400-e29b-41d4-a716-446655440000"
    "reason:rate AND reason:limit"
    "domain:internal AND decision:deny AND time:1700000000-1700003600"

Each clause is either:
    field:value     -- match entries where `field` contains `value`
    time:start-end  -- match entries in timestamp range [start, end]

Multiple clauses joined by AND are intersected.

The search engine wraps an InvertedIndex and handles:
    1. Parsing the query string into clauses
    2. Dispatching field and time clauses
    3. Returning matched entry indices (or reconstructed entries
       if a store reference is provided)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chronoguard_lite.strings.inverted_index import InvertedIndex

if TYPE_CHECKING:
    from chronoguard_lite.domain.audit import AuditEntry


class QueryParseError(Exception):
    """Raised when a query string cannot be parsed."""


class AuditSearchEngine:
    """Search engine over audit entries with a simple query language.

    Usage:
        engine = AuditSearchEngine()
        for entry in entries:
            engine.index_entry(entry)

        indices = engine.search("domain:openai AND decision:DENY")
    """

    def __init__(self) -> None:
        self._index = InvertedIndex()
        self._entries: list[AuditEntry] = []

    @property
    def entry_count(self) -> int:
        return self._index.entry_count

    def index_entry(self, entry: AuditEntry) -> None:
        """Add an entry to the search index."""
        self._index.add_entry(entry)
        self._entries.append(entry)

    def search(self, query: str) -> list[int]:
        """Parse and execute a query, returning matching entry indices.

        Query syntax: "field:value [AND field:value ...]"
        Special field: "time:start-end" for timestamp range.
        """
        clauses = self._parse(query)
        if not clauses:
            return []

        field_clauses: list[tuple[str, str]] = []
        time_sets: list[set[int]] = []

        for field_name, value in clauses:
            if field_name == "time":
                # Parse time range: "start-end"
                parts = value.split("-", 1)
                if len(parts) != 2:
                    raise QueryParseError(
                        f"time clause must be 'start-end', got '{value}'"
                    )
                try:
                    start = float(parts[0])
                    end = float(parts[1])
                except ValueError:
                    raise QueryParseError(
                        f"time values must be numeric, got '{value}'"
                    )
                time_sets.append(self._index.search_time_range(start, end))
            else:
                field_clauses.append((field_name, value))

        # Start with field clause intersection
        if field_clauses:
            result = self._index.search_and(field_clauses)
        elif time_sets:
            result = time_sets[0]
            time_sets = time_sets[1:]
        else:
            return []

        # Intersect with time ranges
        for ts in time_sets:
            result = result & ts
            if not result:
                return []

        return sorted(result)

    def search_entries(self, query: str) -> list[AuditEntry]:
        """Search and return full AuditEntry objects."""
        indices = self.search(query)
        return [self._entries[i] for i in indices]

    def _parse(self, query: str) -> list[tuple[str, str]]:
        """Parse a query string into (field, value) pairs.

        Splits on " AND " (case-sensitive), then splits each
        clause on ":" into field and value.
        """
        query = query.strip()
        if not query:
            return []

        parts = query.split(" AND ")
        clauses: list[tuple[str, str]] = []
        for part in parts:
            part = part.strip()
            if ":" not in part:
                raise QueryParseError(
                    f"Each clause must be 'field:value', got '{part}'"
                )
            field_name, value = part.split(":", 1)
            field_name = field_name.strip()
            value = value.strip()
            if not field_name or not value:
                raise QueryParseError(
                    f"Empty field or value in clause '{part}'"
                )
            clauses.append((field_name, value))
        return clauses

    def naive_search(self, query: str) -> list[int]:
        """Brute-force linear scan for benchmarking comparison.

        Parses the same query syntax but scans every entry instead
        of using the inverted index.
        """
        clauses = self._parse(query)
        if not clauses:
            return []

        results: list[int] = []
        for i, entry in enumerate(self._entries):
            if self._entry_matches_all(entry, clauses):
                results.append(i)
        return results

    def _entry_matches_all(
        self,
        entry: AuditEntry,
        clauses: list[tuple[str, str]],
    ) -> bool:
        """Check if an entry matches all clauses (for naive scan)."""
        for field_name, value in clauses:
            if field_name == "domain":
                if value.lower() not in entry.domain.lower():
                    return False
            elif field_name == "agent_id":
                if value not in str(entry.agent_id):
                    return False
            elif field_name == "decision":
                if value.upper() != entry.decision.name:
                    return False
            elif field_name == "reason":
                if value.lower() not in entry.reason.lower():
                    return False
            elif field_name == "time":
                parts = value.split("-", 1)
                start = float(parts[0])
                end = float(parts[1])
                if not (start <= entry.timestamp <= end):
                    return False
            else:
                return False
        return True
