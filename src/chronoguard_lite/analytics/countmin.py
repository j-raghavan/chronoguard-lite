"""Count-Min Sketch for frequency estimation.

Answers the question: "How many times has this domain been accessed?"
Uses a fixed ~40 KB regardless of how many domains or events pass
through it. The tradeoff: it never underestimates, but it can
overestimate by a bounded amount.

The data structure is a 2D array of counters (depth x width). Each
row uses a different hash function. To increment, hash the item with
each row's hash and increment the corresponding counter. To query,
hash with each row's hash and return the minimum counter value.

The minimum-of-rows trick is what makes it useful: any single row
might have collisions that inflate the count, but the minimum across
independent rows is unlikely to be inflated by much.

Error bound: with probability >= 1 - delta, the estimate overestimates
the true count by at most epsilon * N, where N is the total number
of increments. Default parameters (width=2048, depth=5) give
epsilon ~= e/2048 ~= 0.0013, delta ~= e^-5 ~= 0.0067.

References:
    Cormode & Muthukrishnan, "An Improved Data Stream Summary:
    The Count-Min Sketch and its Applications", 2005.
"""

from __future__ import annotations

import array
import hashlib
import math


def _hash_pair(item: str) -> tuple[int, int]:
    """Produce two independent 64-bit hashes from a single SHA-256.

    We split the 256-bit SHA-256 digest into two 64-bit values.
    These serve as h1 and h2 for double hashing: h_i(x) = h1 + i*h2.
    """
    digest = hashlib.sha256(item.encode("utf-8")).digest()
    h1 = int.from_bytes(digest[:8], "big")
    h2 = int.from_bytes(digest[8:16], "big")
    return h1, h2


class CountMinSketch:
    """Count-Min Sketch for approximate frequency counting.

    Parameters:
        width: Number of counters per row (default 2048).
        depth: Number of rows / hash functions (default 5).

    Memory: width * depth * 4 bytes (uint32 counters).
    With defaults: 2048 * 5 * 4 = 40,960 bytes (~40 KB).
    """

    def __init__(self, width: int = 2048, depth: int = 5) -> None:
        if width < 1 or depth < 1:
            raise ValueError(f"width and depth must be positive, got {width}, {depth}")
        self._width = width
        self._depth = depth
        self._total = 0
        # Each row is an array of uint32 counters
        self._tables: list[array.array] = [
            array.array("I", (0 for _ in range(width)))
            for _ in range(depth)
        ]

    @property
    def width(self) -> int:
        return self._width

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def total(self) -> int:
        """Total number of increment operations."""
        return self._total

    def add(self, item: str, count: int = 1) -> None:
        """Increment the count for an item."""
        h1, h2 = _hash_pair(item)
        for i in range(self._depth):
            idx = (h1 + i * h2) % self._width
            self._tables[i][idx] += count
        self._total += count

    def estimate(self, item: str) -> int:
        """Estimate the count for an item.

        Returns the minimum counter value across all rows.
        This is always >= the true count and <= true count + epsilon * N.
        """
        h1, h2 = _hash_pair(item)
        result = self._tables[0][(h1 + 0 * h2) % self._width]
        for i in range(1, self._depth):
            idx = (h1 + i * h2) % self._width
            val = self._tables[i][idx]
            if val < result:
                result = val
        return result

    def memory_bytes(self) -> int:
        """Approximate memory used by the counter tables."""
        return self._width * self._depth * 4  # 4 bytes per uint32

    def epsilon(self) -> float:
        """Error bound: overestimate <= epsilon * total with prob >= 1-delta."""
        return math.e / self._width

    def delta(self) -> float:
        """Failure probability: P(overestimate > epsilon * total) <= delta."""
        return math.e ** (-self._depth)
