"""DomainMatcher: wildcard domain pattern matching for policy rules.

Wraps both the DomainTrie (for single-domain lookups) and the
AhoCorasick automaton (for matching a domain against many patterns
in a single pass). This is the replacement for the naive
segment-by-segment loop in PolicyRule.matches().

Usage:
    matcher = DomainMatcher()
    matcher.add_pattern("*.openai.com")
    matcher.add_pattern("api.stripe.com")
    matcher.add_pattern("*.*.internal")
    matcher.build()  # required before matching

    matcher.match("api.openai.com")
    # ["*.openai.com"]

    matcher.match("api.staging.internal")
    # ["*.*.internal"]

Internally, both the trie and the Aho-Corasick automaton are built
from the same set of patterns. The trie is used for match() by default
because it naturally handles wildcards through recursive DFS. The
Aho-Corasick automaton is exposed separately via match_ac() for
benchmarking and for the multi-pattern streaming use case.
"""

from __future__ import annotations

from chronoguard_lite.strings.aho_corasick import AhoCorasick
from chronoguard_lite.strings.trie import DomainTrie


class DomainMatcher:
    """Match domains against a set of wildcard patterns.

    Supports three pattern types:
        "api.openai.com"      -- exact match (no wildcards)
        "*.openai.com"        -- single wildcard segment
        "api.*.internal"      -- wildcard in any position
        "*.*.internal"        -- multiple wildcards

    Each "*" matches exactly one domain segment.
    """

    def __init__(self) -> None:
        self._trie = DomainTrie()
        self._ac = AhoCorasick()
        self._built = False
        self._patterns: list[str] = []

    @property
    def pattern_count(self) -> int:
        return len(self._patterns)

    def add_pattern(self, pattern: str) -> None:
        """Add a domain pattern. Call build() after adding all patterns."""
        self._trie.insert(pattern)
        self._ac.add_pattern(pattern)
        self._patterns.append(pattern)
        self._built = False

    def build(self) -> None:
        """Build the Aho-Corasick automaton. The trie is always ready."""
        self._ac.build()
        self._built = True

    def match(self, domain: str) -> list[str]:
        """Match a domain using the trie (recursive DFS).

        Returns all matching patterns. No build() required for trie,
        but call build() anyway for consistency.
        """
        return self._trie.match(domain)

    def match_ac(self, domain: str) -> list[str]:
        """Match a domain using the Aho-Corasick automaton.

        Requires build() to have been called. Returns all matching
        patterns. This is the single-pass variant intended for
        streaming use cases or benchmarking.
        """
        if not self._built:
            raise RuntimeError("Must call build() before match_ac()")
        return self._ac.search(domain)

    def match_naive(self, domain: str) -> list[str]:
        """Naive O(n) scan: test every pattern individually.

        This is the baseline for benchmarking. It uses the same
        segment-by-segment comparison as PolicyRule.matches().
        """
        domain_parts = domain.split(".")
        results: list[str] = []
        for pattern in self._patterns:
            pattern_parts = pattern.split(".")
            if len(pattern_parts) != len(domain_parts):
                continue
            if all(
                pp == "*" or pp == dp
                for pp, dp in zip(pattern_parts, domain_parts)
            ):
                results.append(pattern)
        return results
