"""Bloom filter for membership testing.

Answers the question: "Has agent X ever accessed domain Y?" without
storing every (agent, domain) pair. False positives are possible
(the filter says "maybe" when the answer is "no"), but false negatives
are not (if the filter says "no", the item was never added).

The filter is a bit array of m bits with k hash functions. To add an
item, set bits h_1(item), h_2(item), ..., h_k(item). To query, check
if all k bits are set. We use the double-hashing technique from
Kirsch & Mitzenmacher (2006): h_i(x) = h1(x) + i * h2(x) mod m,
which gives k independent-enough hash functions from a single SHA-256.

References:
    Bloom, "Space/time trade-offs in hash coding with allowable errors", 1970.
    Kirsch & Mitzenmacher, "Less hashing, same performance", 2006.
"""

from __future__ import annotations

import array
import hashlib
import math


def _optimal_size(expected: int, fp_rate: float) -> int:
    """Compute optimal bit array size m for given capacity and FP rate.

    m = -(n * ln(p)) / (ln(2)^2)
    """
    if expected <= 0:
        raise ValueError(f"expected must be positive, got {expected}")
    if not (0.0 < fp_rate < 1.0):
        raise ValueError(f"fp_rate must be in (0, 1), got {fp_rate}")
    m = -(expected * math.log(fp_rate)) / (math.log(2) ** 2)
    return max(64, int(math.ceil(m)))  # at least 64 bits


def _optimal_hashes(m: int, expected: int) -> int:
    """Compute optimal number of hash functions k.

    k = (m / n) * ln(2)
    """
    k = (m / expected) * math.log(2)
    return max(1, int(round(k)))


def _hash_pair(item: str) -> tuple[int, int]:
    """Two 64-bit hashes from SHA-256 for double hashing."""
    digest = hashlib.sha256(item.encode("utf-8")).digest()
    h1 = int.from_bytes(digest[:8], "big")
    h2 = int.from_bytes(digest[8:16], "big")
    return h1, h2


class BloomFilter:
    """Bloom filter for approximate set membership.

    Parameters:
        expected_elements: Expected number of items to be added.
        fp_rate: Target false positive rate (default 0.01 = 1%).

    The filter auto-sizes the bit array and number of hash functions
    to achieve the target FP rate at the given capacity. Going beyond
    the expected capacity degrades the FP rate but never causes false
    negatives.
    """

    def __init__(
        self,
        expected_elements: int = 1_000_000,
        fp_rate: float = 0.01,
    ) -> None:
        self._expected = expected_elements
        self._target_fp = fp_rate
        self._m = _optimal_size(expected_elements, fp_rate)
        self._k = _optimal_hashes(self._m, expected_elements)
        self._count = 0

        # Bit array stored as uint64 words for efficiency
        num_words = (self._m + 63) // 64
        self._bits = array.array("Q", (0 for _ in range(num_words)))

    @property
    def size_bits(self) -> int:
        """Number of bits in the filter."""
        return self._m

    @property
    def num_hashes(self) -> int:
        """Number of hash functions."""
        return self._k

    @property
    def count(self) -> int:
        """Number of items added."""
        return self._count

    def add(self, item: str) -> None:
        """Add an item to the filter."""
        h1, h2 = _hash_pair(item)
        for i in range(self._k):
            bit_pos = (h1 + i * h2) % self._m
            word_idx = bit_pos >> 6  # // 64
            bit_idx = bit_pos & 63   # % 64
            self._bits[word_idx] |= (1 << bit_idx)
        self._count += 1

    def might_contain(self, item: str) -> bool:
        """Check if an item might be in the filter.

        Returns True if the item is probably in the set (could be a
        false positive). Returns False if the item is definitely not
        in the set (never a false negative).
        """
        h1, h2 = _hash_pair(item)
        for i in range(self._k):
            bit_pos = (h1 + i * h2) % self._m
            word_idx = bit_pos >> 6
            bit_idx = bit_pos & 63
            if not (self._bits[word_idx] & (1 << bit_idx)):
                return False
        return True

    def fill_ratio(self) -> float:
        """Fraction of bits that are set."""
        set_bits = 0
        for word in self._bits:
            set_bits += bin(word).count("1")
        return set_bits / self._m

    def estimated_fp_rate(self) -> float:
        """Estimate current false positive rate based on fill ratio.

        FP rate ~= (fill_ratio)^k
        This is more accurate than the theoretical rate when the actual
        number of items added differs from expected_elements.
        """
        fr = self.fill_ratio()
        if fr >= 1.0:
            return 1.0
        return fr ** self._k

    def memory_bytes(self) -> int:
        """Approximate memory used by the bit array."""
        return len(self._bits) * 8  # 8 bytes per uint64 word
