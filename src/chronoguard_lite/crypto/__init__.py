"""Cryptographic audit chain -- SHA256 and HMAC-SHA256 hash chaining.

Public API:
    AuditHasher functions: hash_entry, hmac_entry, generate_secret_key
    AuditChain: append-only hash chain
    ChainedEntry: entry wrapper with chain metadata
    ChainVerifier: tamper detection
    ChainVerificationResult: verification outcome
"""

from chronoguard_lite.crypto.chain import (
    GENESIS_HASH,
    AuditChain,
    ChainedEntry,
)
from chronoguard_lite.crypto.hasher import (
    generate_secret_key,
    hash_entry,
    hmac_entry,
)
from chronoguard_lite.crypto.verifier import (
    ChainVerificationResult,
    ChainVerifier,
)

__all__ = [
    "GENESIS_HASH",
    "AuditChain",
    "ChainedEntry",
    "ChainVerificationResult",
    "ChainVerifier",
    "generate_secret_key",
    "hash_entry",
    "hmac_entry",
]
