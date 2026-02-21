"""HyperLogLog cardinality estimator.

Answers the question: "How many distinct agents accessed this domain?"
without storing every agent ID. Uses ~2 KB of memory per counter
regardless of how many unique items you feed it, at the cost of
roughly 2-3% standard error.

The algorithm works by hashing each item, splitting the hash into a
register index (top p bits) and a value (position of the first 1-bit
in the remaining bits). The maximum observed leading-zero count in
each register is a noisy estimate of log2(cardinality). Averaging
across 2^p registers with a harmonic mean gives a usable estimate.

References:
    Flajolet et al., "HyperLogLog: the analysis of a near-optimal
    cardinality estimation algorithm", 2007.
"""

from __future__ import annotations

import array
import hashlib
import math


def _hash64(item: str) -> int:
    """Hash a string to a 64-bit integer using SHA-256 truncated."""
    digest = hashlib.sha256(item.encode("utf-8")).digest()
    # Take the first 8 bytes as a big-endian uint64
    return int.from_bytes(digest[:8], "big")


def _leading_zeros_plus_one(value: int, max_bits: int) -> int:
    """Count leading zeros in the low `max_bits` bits, then add 1.

    The "+1" convention means the minimum return value is 1 (when the
    highest bit is set) and the maximum is max_bits + 1 (when all bits
    are zero, which should not happen with a good hash but we handle
    it defensively).
    """
    if value == 0:
        return max_bits + 1
    # Count from the top of the max_bits window
    count = 0
    mask = 1 << (max_bits - 1)
    while (value & mask) == 0:
        count += 1
        mask >>= 1
    return count + 1


class HyperLogLog:
    """HyperLogLog cardinality estimator.

    Parameters:
        p: Precision parameter. Uses 2^p registers (default 11 = 2048
           registers = ~2 KB). Higher p = more accuracy, more memory.
           Standard error is approximately 1.04 / sqrt(2^p).

    Typical precision values:
        p=10: 1024 registers, ~1 KB, ~3.25% error
        p=11: 2048 registers, ~2 KB, ~2.30% error
        p=12: 4096 registers, ~4 KB, ~1.63% error
        p=14: 16384 registers, ~16 KB, ~0.81% error
    """

    def __init__(self, p: int = 11) -> None:
        if not (4 <= p <= 18):
            raise ValueError(f"Precision p must be 4..18, got {p}")
        self._p = p
        self._m = 1 << p  # number of registers
        self._registers = array.array("B", b"\x00" * self._m)
        # Alpha constant for bias correction (from the HLL paper)
        if self._m == 16:
            self._alpha = 0.673
        elif self._m == 32:
            self._alpha = 0.697
        elif self._m == 64:
            self._alpha = 0.709
        else:
            self._alpha = 0.7213 / (1.0 + 1.079 / self._m)

    @property
    def precision(self) -> int:
        return self._p

    @property
    def num_registers(self) -> int:
        return self._m

    def add(self, item: str) -> None:
        """Add an item to the counter."""
        h = _hash64(item)
        # Top p bits select the register
        idx = h >> (64 - self._p)
        # Remaining bits are used for the leading-zeros count
        remaining = h & ((1 << (64 - self._p)) - 1)
        rank = _leading_zeros_plus_one(remaining, 64 - self._p)
        if rank > self._registers[idx]:
            self._registers[idx] = rank

    def count(self) -> int:
        """Estimate the number of distinct items added.

        Applies small-range correction (linear counting) when many
        registers are still zero, and caps at 2^64 for large ranges.
        """
        # Raw harmonic mean estimate
        indicator = sum(2.0 ** (-r) for r in self._registers)
        raw = self._alpha * self._m * self._m / indicator

        # Small range correction: linear counting
        if raw <= 2.5 * self._m:
            zeros = self._registers.count(0)
            if zeros > 0:
                # Linear counting estimate
                return int(self._m * math.log(self._m / zeros))
            return int(raw)

        # Large range correction (only matters near 2^64)
        two_pow_64 = 2.0 ** 64
        if raw > two_pow_64 / 30.0:
            return int(-two_pow_64 * math.log(1.0 - raw / two_pow_64))

        return int(raw)

    def merge(self, other: HyperLogLog) -> None:
        """Merge another HyperLogLog into this one (union operation).

        After merging, this counter estimates the cardinality of the
        union of items added to both counters.
        """
        if self._p != other._p:
            raise ValueError(
                f"Cannot merge HLLs with different precision: "
                f"{self._p} vs {other._p}"
            )
        for i in range(self._m):
            if other._registers[i] > self._registers[i]:
                self._registers[i] = other._registers[i]

    def memory_bytes(self) -> int:
        """Approximate memory used by the registers."""
        return self._m  # 1 byte per register

    def standard_error(self) -> float:
        """Theoretical standard error for this precision."""
        return 1.04 / math.sqrt(self._m)
