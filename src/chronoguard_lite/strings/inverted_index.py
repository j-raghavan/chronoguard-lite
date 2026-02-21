"""Inverted index for fast audit entry search.

An inverted index maps terms to the set of document IDs (here,
entry indices) that contain those terms. Instead of scanning every
entry to find matches, you look up the term and get the answer
directly.

Our index stores four fields from AuditEntry:
    - domain: tokenized by "." so "api.openai.com" produces
      tokens ["api", "openai", "com"]. This lets you search
      for partial domain matches.
    - agent_id: stored as the full UUID string (no tokenization).
    - decision: stored as the enum name ("ALLOW", "DENY", etc).
    - reason: tokenized by whitespace and lowercased.

Each field has its own posting lists (term -> set of entry indices)
to support field-scoped queries like "domain:openai".

Building the index is O(n * avg_tokens_per_entry). Querying is
O(k) where k is the size of the smallest posting list in the query,
because we intersect posting lists. This is the fundamental speedup
over linear scan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronoguard_lite.domain.audit import AuditEntry


class InvertedIndex:
    """Field-scoped inverted index over AuditEntry objects.

    Call add_entry() for each entry, then use search_field() or
    search_and() to query. Entry indices are 0-based and correspond
    to the order entries were added.
    """

    def __init__(self) -> None:
        # field_name -> {term -> set of entry indices}
        self._postings: dict[str, dict[str, set[int]]] = {
            "domain": {},
            "agent_id": {},
            "decision": {},
            "reason": {},
        }
        self._count = 0
        # Store timestamps for time-range filtering
        self._timestamps: list[float] = []

    @property
    def entry_count(self) -> int:
        return self._count

    def add_entry(self, entry: AuditEntry) -> None:
        """Index an entry. The entry index is self._count (0-based)."""
        idx = self._count

        # Domain: tokenize by "."
        for token in entry.domain.split("."):
            tok_lower = token.lower()
            posting = self._postings["domain"]
            if tok_lower not in posting:
                posting[tok_lower] = set()
            posting[tok_lower].add(idx)

        # Also index the full domain string for exact match
        full_domain = entry.domain.lower()
        posting = self._postings["domain"]
        if full_domain not in posting:
            posting[full_domain] = set()
        posting[full_domain].add(idx)

        # Agent ID: full string
        agent_str = str(entry.agent_id)
        posting = self._postings["agent_id"]
        if agent_str not in posting:
            posting[agent_str] = set()
        posting[agent_str].add(idx)

        # Decision: enum name
        dec = entry.decision.name
        posting = self._postings["decision"]
        if dec not in posting:
            posting[dec] = set()
        posting[dec].add(idx)

        # Reason: tokenize by whitespace, lowercase
        for word in entry.reason.split():
            w = word.lower().strip(".,;:!?()[]")
            if not w:
                continue
            posting = self._postings["reason"]
            if w not in posting:
                posting[w] = set()
            posting[w].add(idx)

        self._timestamps.append(entry.timestamp)
        self._count += 1

    def search_field(self, field: str, term: str) -> set[int]:
        """Look up a single term in a single field.

        Returns a set of entry indices. Returns empty set if the
        term is not found.
        """
        field_upper = field.lower()
        if field_upper == "decision":
            term = term.upper()
        else:
            term = term.lower()
        posting = self._postings.get(field, {})
        return set(posting.get(term, set()))

    def search_and(self, clauses: list[tuple[str, str]]) -> set[int]:
        """AND-query: intersect posting lists for multiple (field, term) pairs.

        Returns the set of entry indices matching ALL clauses.
        Starts with the smallest posting list for efficiency.
        """
        if not clauses:
            return set()

        # Get all posting lists, sorted by size (smallest first)
        lists: list[set[int]] = []
        for field_name, term in clauses:
            s = self.search_field(field_name, term)
            if not s:
                return set()  # short-circuit: empty intersection
            lists.append(s)
        lists.sort(key=len)

        result = lists[0]
        for other in lists[1:]:
            result = result & other
            if not result:
                return set()
        return result

    def search_time_range(self, start: float, end: float) -> set[int]:
        """Return entry indices whose timestamp falls in [start, end]."""
        # Linear scan over timestamps. For a production system you
        # would use bisect on a sorted array, but the inverted index
        # stores entries in insertion order (not necessarily sorted).
        result: set[int] = set()
        for i, ts in enumerate(self._timestamps):
            if start <= ts <= end:
                result.add(i)
        return result

    def term_count(self, field: str) -> int:
        """Number of distinct terms in a field's posting lists."""
        return len(self._postings.get(field, {}))

    def memory_estimate_bytes(self) -> int:
        """Rough memory estimate for the posting lists.

        Each set entry is roughly 28 bytes (Python set overhead per int).
        Each dict entry is roughly 64 bytes. This is a rough lower bound.
        """
        total = 0
        for field_postings in self._postings.values():
            total += len(field_postings) * 64  # dict entry overhead
            for s in field_postings.values():
                total += len(s) * 28  # set entry overhead
        total += len(self._timestamps) * 8  # float list
        return total
