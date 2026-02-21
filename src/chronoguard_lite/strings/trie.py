"""Segment-level trie for reversed domain matching.

Domain names are split on "." and reversed before insertion so that
TLD comes first: "api.openai.com" becomes ["com", "openai", "api"].
This lets us share the common suffix (TLD + org) across many patterns
and branch only where domains diverge.

Wildcard segments ("*") are stored as regular children with the key "*".
During lookup, at each node we check both the literal segment child
and the "*" child, collecting all matching patterns.

This is not an Aho-Corasick automaton. It handles one domain against
many patterns efficiently (O(depth) per lookup, where depth = number
of segments), but it traverses the trie per-domain rather than
streaming through an automaton. For single-pass multi-pattern matching,
see aho_corasick.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrieNode:
    """A node in the domain trie.

    children maps a segment string (or "*") to the next node.
    patterns stores the original pattern strings that terminate here.
    """
    children: dict[str, TrieNode] = field(default_factory=dict)
    patterns: list[str] = field(default_factory=list)


class DomainTrie:
    """Trie over reversed domain segments for wildcard pattern matching.

    Supports patterns like:
        "api.openai.com"      -- exact match
        "*.openai.com"        -- wildcard prefix (one segment)
        "api.*.internal"      -- wildcard in middle
        "*.*.internal"        -- multiple wildcards

    Each "*" matches exactly one segment. It does NOT match zero
    segments or multiple segments (no globstar semantics).
    """

    def __init__(self) -> None:
        self._root = TrieNode()
        self._pattern_count = 0

    @property
    def pattern_count(self) -> int:
        return self._pattern_count

    def insert(self, pattern: str) -> None:
        """Insert a domain pattern into the trie.

        The pattern is split on "." and reversed so that the TLD
        comes first. Each segment (including "*") becomes a trie edge.
        """
        segments = pattern.split(".")
        segments.reverse()
        node = self._root
        for seg in segments:
            if seg not in node.children:
                node.children[seg] = TrieNode()
            node = node.children[seg]
        node.patterns.append(pattern)
        self._pattern_count += 1

    def match(self, domain: str) -> list[str]:
        """Return all patterns matching the given domain.

        Splits the domain, reverses it, and walks the trie. At each
        level, follows both the exact-match child and the "*" child
        (if present), collecting all terminating patterns at the
        correct depth.
        """
        segments = domain.split(".")
        segments.reverse()
        results: list[str] = []
        self._walk(self._root, segments, 0, results)
        return results

    def _walk(
        self,
        node: TrieNode,
        segments: list[str],
        depth: int,
        results: list[str],
    ) -> None:
        """Recursive DFS through the trie, branching on literal and wildcard."""
        if depth == len(segments):
            # We have consumed all segments. Collect patterns here.
            results.extend(node.patterns)
            return

        seg = segments[depth]

        # Exact match on this segment
        child = node.children.get(seg)
        if child is not None:
            self._walk(child, segments, depth + 1, results)

        # Wildcard match (if pattern had "*" at this depth)
        wild = node.children.get("*")
        if wild is not None:
            self._walk(wild, segments, depth + 1, results)

    def node_count(self) -> int:
        """Count total nodes in the trie (for memory reporting)."""
        count = 0
        stack = [self._root]
        while stack:
            node = stack.pop()
            count += 1
            stack.extend(node.children.values())
        return count
