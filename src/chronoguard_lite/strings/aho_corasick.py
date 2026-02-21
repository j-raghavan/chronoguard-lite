"""Aho-Corasick automaton for multi-pattern domain matching.

The classic Aho-Corasick algorithm (1975) builds a finite automaton
from a set of patterns and then scans an input string in a single
pass, reporting all pattern matches. It consists of three phases:

    1. Build the goto trie: insert each pattern segment by segment.
    2. Compute failure links (BFS from root): when a match fails at
       a node, the failure link points to the longest proper suffix
       of the current path that is also a prefix of some pattern.
    3. Compute output/dictionary links: each node's output is its
       own patterns (if any) plus the patterns reachable via its
       failure link chain.

Our variant operates on domain *segments* rather than characters.
A domain like "api.openai.com" becomes the segment sequence
["api", "openai", "com"]. Patterns like "*.openai.com" become
["*", "openai", "com"]. The wildcard "*" is treated as a literal
segment label in the automaton; wildcard expansion happens in the
search step by feeding both the actual segment and "*" at each
position.

This is the hardest algorithm in the book. The failure link
computation is subtle, and getting it wrong produces silent
incorrect results rather than crashes.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class ACNode:
    """A node in the Aho-Corasick automaton."""
    children: dict[str, ACNode] = field(default_factory=dict)
    fail: ACNode | None = None
    output: list[str] = field(default_factory=list)
    depth: int = 0


class AhoCorasick:
    """Aho-Corasick automaton operating on domain segments.

    Usage:
        ac = AhoCorasick()
        ac.add_pattern("*.openai.com")
        ac.add_pattern("api.stripe.com")
        ac.build()  # MUST call before searching
        matches = ac.search("api.openai.com")
        # returns ["*.openai.com"]

    The build() step computes failure and output links. Calling
    add_pattern() after build() invalidates the automaton; you must
    call build() again.
    """

    def __init__(self) -> None:
        self._root = ACNode()
        self._built = False
        self._pattern_count = 0

    @property
    def pattern_count(self) -> int:
        return self._pattern_count

    def add_pattern(self, pattern: str) -> None:
        """Insert a domain pattern into the goto trie.

        Patterns are stored in their original segment order (not reversed).
        """
        segments = pattern.split(".")
        node = self._root
        for i, seg in enumerate(segments):
            if seg not in node.children:
                node.children[seg] = ACNode(depth=i + 1)
            node = node.children[seg]
        node.output.append(pattern)
        self._pattern_count += 1
        self._built = False

    def build(self) -> None:
        """Compute failure links and propagate output lists.

        Failure link computation (BFS):
        - Root's children all have fail -> root.
        - For each node at depth >= 2, follow the parent's failure
          link and look for a child matching the current segment.
          If found, that is the failure target. If not, follow the
          failure link's failure link, and repeat until root.

        Output propagation:
        - After setting a node's failure link, append the failure
          target's output list to the node's output list. This
          catches shorter patterns that are suffixes of longer ones.
        """
        root = self._root
        root.fail = root
        queue: deque[ACNode] = deque()

        # Depth-1 nodes: failure link -> root
        for child in root.children.values():
            child.fail = root
            queue.append(child)

        # BFS for depth >= 2
        while queue:
            current = queue.popleft()
            for seg, child in current.children.items():
                # Walk up failure links to find the longest matching suffix
                fallback = current.fail
                while fallback is not root and seg not in fallback.children:
                    fallback = fallback.fail  # type: ignore[assignment]
                child.fail = fallback.children.get(seg, root)
                if child.fail is child:
                    # Avoid self-loop: if the only match is ourselves, point to root
                    child.fail = root
                # Propagate outputs from the failure chain
                child.output = child.output + child.fail.output
                queue.append(child)

        self._built = True

    def search(self, domain: str) -> list[str]:
        """Find all patterns matching the given domain.

        Walks the automaton segment by segment. At each position,
        feeds both the literal segment and "*" to handle wildcard
        patterns. Collects outputs from all reached nodes.

        Returns a deduplicated list of matched pattern strings.
        """
        if not self._built:
            raise RuntimeError("Must call build() before search()")

        segments = domain.split(".")
        results: list[str] = []
        seen: set[str] = set()

        # We track a set of active states (nodes in the automaton).
        # At each segment, each active state tries to advance via
        # the literal segment and via "*", following failure links
        # on mismatch.
        active: set[int] = {id(self._root)}
        active_nodes: dict[int, ACNode] = {id(self._root): self._root}

        for seg in segments:
            next_active: dict[int, ACNode] = {}
            for node in active_nodes.values():
                # Try advancing with literal segment
                self._advance(node, seg, next_active)
                # Try advancing with wildcard
                self._advance(node, "*", next_active)
            active_nodes = next_active

        # Collect outputs from all final active states, but only if
        # the pattern has the same number of segments as the domain.
        # Without this check, a 3-segment pattern like "*.openai.com"
        # could match a 4-segment domain like "api.v2.openai.com"
        # because the automaton's failure links propagate outputs
        # to deeper nodes.
        n_segments = len(segments)
        for node in active_nodes.values():
            for pat in node.output:
                if pat not in seen and pat.count(".") + 1 == n_segments:
                    seen.add(pat)
                    results.append(pat)

        return results

    def _advance(
        self,
        node: ACNode,
        seg: str,
        next_active: dict[int, ACNode],
    ) -> None:
        """Advance from `node` on segment `seg`, following failure links."""
        current = node
        root = self._root
        while current is not root and seg not in current.children:
            current = current.fail  # type: ignore[assignment]
        target = current.children.get(seg)
        if target is not None:
            nid = id(target)
            if nid not in next_active:
                next_active[nid] = target

    def node_count(self) -> int:
        """Count total nodes in the automaton."""
        count = 0
        stack = [self._root]
        visited: set[int] = set()
        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            count += 1
            stack.extend(node.children.values())
        return count
