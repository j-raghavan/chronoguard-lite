"""Chain verification with detailed tamper detection.

The ChainVerifier walks an AuditChain and recomputes every hash from
scratch. If any stored hash doesn't match the recomputed hash, it
reports exactly where the chain broke, what the expected hash was, and
what it found instead.

Three verification modes:
- verify_full(): Walk the entire chain from genesis. O(n) time, but
  guarantees the whole chain is intact.
- verify_range(start, end): Verify a slice. Useful for incremental
  checks, but requires trusting the entry at start-1.
- verify_entry(seq): Verify a single entry against its predecessor.
  O(1) but only proves that one link is intact.
"""

from __future__ import annotations

from dataclasses import dataclass

from chronoguard_lite.crypto.chain import GENESIS_HASH, AuditChain
from chronoguard_lite.crypto.hasher import hash_entry, hmac_entry


@dataclass(frozen=True, slots=True)
class ChainVerificationResult:
    """Result of a chain verification operation."""

    is_valid: bool
    entries_verified: int
    first_invalid_sequence: int | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    error_message: str | None = None


class ChainVerifier:
    """Verifies the integrity of an AuditChain.

    The verifier recomputes hashes from the raw entry fields and
    compares them to the stored hashes. It uses the same hashing
    mode (plain SHA256 or HMAC-SHA256) as the chain was built with.
    """

    def __init__(self, chain: AuditChain) -> None:
        self._chain = chain

    def verify_full(self) -> ChainVerificationResult:
        """Verify the entire chain from genesis to head.

        Walks every entry, recomputes its hash, and checks it against
        the stored hash. Stops at the first mismatch.

        Time complexity: O(n) where n = number of entries.
        """
        if len(self._chain) == 0:
            return ChainVerificationResult(is_valid=True, entries_verified=0)

        return self._verify_range_internal(0, len(self._chain))

    def verify_range(self, start: int, end: int) -> ChainVerificationResult:
        """Verify a contiguous slice of the chain.

        Verifies entries[start] through entries[end-1]. The entry at
        `start` is verified against its stored previous_hash -- this
        means you're trusting that previous_hash is correct. For full
        integrity, use verify_full().

        Raises ValueError if start or end is out of bounds.
        """
        chain_len = len(self._chain)
        if start < 0 or end > chain_len or start >= end:
            raise ValueError(
                f"Invalid range [{start}, {end}) for chain of length {chain_len}"
            )
        return self._verify_range_internal(start, end)

    def verify_entry(self, sequence_number: int) -> ChainVerificationResult:
        """Verify a single entry against its predecessor.

        Checks that entry[seq].current_hash matches a fresh recomputation
        using entry[seq].previous_hash. This only proves that this one
        link is intact -- it doesn't verify the predecessor itself.

        Raises IndexError if sequence_number is out of range.
        """
        chained = self._chain.get(sequence_number)
        recomputed = self._compute_hash(chained.entry, chained.previous_hash)

        if recomputed == chained.current_hash:
            return ChainVerificationResult(
                is_valid=True, entries_verified=1
            )

        return ChainVerificationResult(
            is_valid=False,
            entries_verified=0,
            first_invalid_sequence=sequence_number,
            expected_hash=recomputed,
            actual_hash=chained.current_hash,
            error_message=(
                f"Hash mismatch at sequence {sequence_number}: "
                f"expected {recomputed[:16]}..., "
                f"got {chained.current_hash[:16]}..."
            ),
        )

    def _verify_range_internal(
        self, start: int, end: int
    ) -> ChainVerificationResult:
        """Internal range verification logic."""
        secret_key = self._chain.secret_key
        verified = 0

        for seq in range(start, end):
            chained = self._chain[seq]

            # For the first entry in the range, use its stored previous_hash.
            # For subsequent entries, the previous hash should match the
            # current hash of the prior entry.
            if seq == 0:
                expected_prev = GENESIS_HASH
            elif seq == start:
                # Start of a range check -- trust the stored previous_hash
                expected_prev = chained.previous_hash
            else:
                expected_prev = self._chain[seq - 1].current_hash

            # Check chain link: does previous_hash match what we expect?
            if chained.previous_hash != expected_prev:
                return ChainVerificationResult(
                    is_valid=False,
                    entries_verified=verified,
                    first_invalid_sequence=seq,
                    expected_hash=expected_prev,
                    actual_hash=chained.previous_hash,
                    error_message=(
                        f"Chain link broken at sequence {seq}: "
                        f"previous_hash does not match predecessor's "
                        f"current_hash. Entry may have been deleted or "
                        f"reordered."
                    ),
                )

            # Recompute hash from scratch
            recomputed = self._compute_hash(chained.entry, chained.previous_hash)
            if recomputed != chained.current_hash:
                return ChainVerificationResult(
                    is_valid=False,
                    entries_verified=verified,
                    first_invalid_sequence=seq,
                    expected_hash=recomputed,
                    actual_hash=chained.current_hash,
                    error_message=(
                        f"Hash mismatch at sequence {seq}: "
                        f"entry fields have been modified. "
                        f"Expected {recomputed[:16]}..., "
                        f"got {chained.current_hash[:16]}..."
                    ),
                )

            verified += 1

        return ChainVerificationResult(
            is_valid=True, entries_verified=verified
        )

    def _compute_hash(self, entry, previous_hash: str) -> str:
        """Recompute a hash using the chain's hashing mode."""
        secret_key = self._chain.secret_key
        if secret_key is not None:
            return hmac_entry(entry, previous_hash, secret_key)
        return hash_entry(entry, previous_hash)
