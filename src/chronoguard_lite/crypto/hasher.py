"""SHA256 and HMAC-SHA256 hashing for audit entries.

The AuditHasher converts an AuditEntry into a deterministic byte
representation (canonicalization), then hashes it with SHA256. For tamper-evident chaining, it supports HMAC-SHA256 where a secret key
binds each hash to a shared secret that an attacker cannot forge
without possessing the key.

Canonicalization is the tricky part. Two entries that differ only in
field ordering or whitespace must produce different canonical forms,
and the same entry must always produce the same bytes regardless of
Python version or platform. We use length-prefixed fields in a fixed
order, with explicit markers for None values and repr() for floats
to avoid platform-dependent formatting.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronoguard_lite.domain.audit import AuditEntry


# Sentinel for None fields in canonical form.
# A single zero byte distinguishes None from any real UUID bytes
# (which are always exactly 16 bytes long).
_NONE_SENTINEL = b"\x00"


def _lp(data: bytes) -> bytes:
    """Length-prefix a byte string with a 4-byte big-endian length.

    This makes the encoding injective: no two different sequences of
    field values can produce the same concatenated byte stream, because
    the decoder can unambiguously split the stream back into fields.
    """
    return struct.pack("!I", len(data)) + data


def _canonicalize(entry: AuditEntry, previous_hash: str) -> bytes:
    """Build a deterministic byte string from an AuditEntry and its chain link.

    Each field is length-prefixed with a 4-byte big-endian length, then
    concatenated. This encoding is injective: two different entries will
    always produce different byte strings. Without length prefixes, raw
    binary fields (like UUID.bytes) could contain bytes that look like
    delimiters, causing two different entries to collide.

    Field order is fixed and must never change once entries have been
    hashed -- changing the order would silently break every existing chain.

    The previous_hash is included in the canonical form so that each
    entry's hash depends on the entire chain before it, not just its
    own fields.
    """
    parts: list[bytes] = [
        _lp(entry.entry_id.bytes),
        _lp(entry.agent_id.bytes),
        _lp(entry.domain.encode("utf-8")),
        _lp(entry.decision.name.encode("ascii")),
        _lp(repr(entry.timestamp).encode("ascii")),
        _lp(entry.reason.encode("utf-8")),
        _lp(entry.policy_id.bytes if entry.policy_id is not None else _NONE_SENTINEL),
        _lp(entry.rule_id.bytes if entry.rule_id is not None else _NONE_SENTINEL),
        _lp(entry.request_method.encode("ascii")),
        _lp(entry.request_path.encode("utf-8")),
        _lp(entry.source_ip.encode("ascii")),
        _lp(repr(entry.processing_time_ms).encode("ascii")),
        _lp(previous_hash.encode("ascii")),
    ]
    return b"".join(parts)


def hash_entry(entry: AuditEntry, previous_hash: str) -> str:
    """Compute SHA256(canonicalize(entry) || previous_hash).

    Returns a 64-character lowercase hex string.
    """
    canonical = _canonicalize(entry, previous_hash)
    return hashlib.sha256(canonical).hexdigest()


def hmac_entry(
    entry: AuditEntry,
    previous_hash: str,
    secret_key: bytes,
) -> str:
    """Compute HMAC-SHA256(secret_key, canonicalize(entry) || previous_hash).

    Returns a 64-character lowercase hex string.

    Why HMAC instead of plain SHA256? Plain SHA256 proves that an entry
    hasn't been modified, but anyone who can read the chain can recompute
    all the hashes after tampering. HMAC binds each hash to a secret key,
    so an attacker who modifies an entry and recomputes the chain will
    produce different hashes unless they also have the key.
    """
    canonical = _canonicalize(entry, previous_hash)
    return hmac.new(secret_key, canonical, hashlib.sha256).hexdigest()


def generate_secret_key() -> bytes:
    """Generate a 32-byte random secret key for HMAC operations.

    Uses os.urandom which pulls from the OS CSPRNG (/dev/urandom on
    Linux, CryptGenRandom on Windows). This is the right source for
    key material -- not random.randbytes(), not secrets.token_bytes()
    (which wraps os.urandom anyway but adds unnecessary abstraction
    for our use case).
    """
    return os.urandom(32)
