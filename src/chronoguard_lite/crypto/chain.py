"""Append-only hash chain for tamper-evident audit logging.

Each AuditEntry is wrapped in a ChainedEntry that stores:
- The entry itself
- The hash of the previous entry in the chain
- The hash of this entry (computed from entry fields + previous hash)
- A monotonically increasing sequence number

The chain starts from a genesis hash (64 zero characters, used as a
fixed sentinel -- not the SHA256 of empty input). Each subsequent
entry's hash depends on all entries before it, so modifying, deleting,
or reordering any entry breaks every hash that follows.

This is the same principle behind blockchain ledgers and git commit
histories. The chain is tamper-evident, not tamper-proof: it detects
modifications but does not prevent them. With plain SHA256, detection
requires comparing against a trusted anchor (e.g., a published head
hash or external checkpoint). With HMAC-SHA256, detection works even
if the attacker has full read/write access to the chain data, as long
as they do not possess the secret key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from chronoguard_lite.crypto.hasher import (
    generate_secret_key,
    hash_entry,
    hmac_entry,
)
from chronoguard_lite.domain.audit import AuditEntry


# The chain starts here. 64 hex zeros is a fixed sentinel, not the
# SHA256 of any particular input.  (SHA256 of b"" is e3b0c44298fc...,
# which is different.)  We use all-zeros because it is obviously
# synthetic and cannot be confused with a real entry hash.
GENESIS_HASH: str = "0" * 64


@dataclass(frozen=True, slots=True)
class ChainedEntry:
    """An AuditEntry wrapped with chain metadata."""

    entry: AuditEntry
    previous_hash: str
    current_hash: str
    sequence_number: int


class AuditChain:
    """Append-only hash chain of audit entries.

    Two modes of operation:
    - Without a secret key: uses plain SHA256. Proves integrity if the
      verifier has a trusted copy of any hash in the chain (e.g., the
      genesis hash or a periodic checkpoint).
    - With a secret key: uses HMAC-SHA256. Proves integrity even if the
      attacker has full read/write access to the chain, as long as they
      don't have the key.

    The chain enforces append-only semantics. There is no delete or
    update method. To "correct" an entry, append a new entry that
    supersedes it -- the original remains in the chain for auditability.
    """

    def __init__(self, secret_key: bytes | None = None) -> None:
        self._entries: list[ChainedEntry] = []
        self._head_hash: str = GENESIS_HASH
        self._secret_key: bytes | None = secret_key

    @classmethod
    def with_hmac(cls, secret_key: bytes | None = None) -> AuditChain:
        """Create a chain that uses HMAC-SHA256 for tamper resistance.

        If no key is provided, generates a random 32-byte key.
        Store this key securely -- you need it for verification.
        """
        if secret_key is None:
            secret_key = generate_secret_key()
        return cls(secret_key=secret_key)

    @property
    def secret_key(self) -> bytes | None:
        """The HMAC secret key, or None if using plain SHA256."""
        return self._secret_key

    @property
    def head_hash(self) -> str:
        """The hash of the most recent entry (or genesis if empty)."""
        return self._head_hash

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, entry: AuditEntry) -> ChainedEntry:
        """Hash and append an entry to the chain.

        Returns the ChainedEntry with computed hashes and sequence number.
        """
        seq = len(self._entries)
        previous = self._head_hash

        if self._secret_key is not None:
            current = hmac_entry(entry, previous, self._secret_key)
        else:
            current = hash_entry(entry, previous)

        chained = ChainedEntry(
            entry=entry,
            previous_hash=previous,
            current_hash=current,
            sequence_number=seq,
        )
        self._entries.append(chained)
        self._head_hash = current
        return chained

    def get(self, sequence_number: int) -> ChainedEntry:
        """Retrieve a chained entry by sequence number.

        Raises IndexError if out of range.
        """
        if sequence_number < 0 or sequence_number >= len(self._entries):
            raise IndexError(
                f"Sequence {sequence_number} out of range "
                f"(chain has {len(self._entries)} entries)"
            )
        return self._entries[sequence_number]

    def __iter__(self) -> Iterator[ChainedEntry]:
        return iter(self._entries)

    def __getitem__(self, index: int) -> ChainedEntry:
        return self._entries[index]
