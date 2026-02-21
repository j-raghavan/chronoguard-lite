"""Tests that the verifier catches various forms of tampering.

These tests deliberately break the chain in different ways and
verify that the verifier detects the exact location and type of
tampering. This is the core of the audit chain's value: you can
prove that no one has modified the historical record.
"""
from __future__ import annotations

import uuid
from dataclasses import replace

from chronoguard_lite.crypto.chain import GENESIS_HASH, AuditChain, ChainedEntry
from chronoguard_lite.crypto.verifier import ChainVerifier

from .conftest import make_entry, generate_entries


def _build_chain(n: int, use_hmac: bool = False) -> AuditChain:
    """Build a valid chain of n entries."""
    if use_hmac:
        chain = AuditChain.with_hmac(secret_key=b"test-key-for-tamper-detection!!!")
    else:
        chain = AuditChain()
    for entry in generate_entries(n):
        chain.append(entry)
    return chain


class TestTamperMiddleEntry:
    """Modify an entry in the middle of the chain."""

    def test_modify_domain_at_500(self):
        chain = _build_chain(1000)
        # Tamper: change the domain of entry 500
        original = chain[500]
        tampered_entry = replace(original.entry, domain="evil.example.com")
        tampered = ChainedEntry(
            entry=tampered_entry,
            previous_hash=original.previous_hash,
            current_hash=original.current_hash,  # hash is now wrong
            sequence_number=original.sequence_number,
        )
        chain._entries[500] = tampered

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        assert result.first_invalid_sequence == 500
        assert result.error_message is not None
        assert "500" in result.error_message

    def test_modify_decision_at_50(self):
        chain = _build_chain(100)
        original = chain[50]
        from chronoguard_lite.domain.decisions import AccessDecision
        tampered_entry = replace(original.entry, decision=AccessDecision.DENY)
        tampered = ChainedEntry(
            entry=tampered_entry,
            previous_hash=original.previous_hash,
            current_hash=original.current_hash,
            sequence_number=original.sequence_number,
        )
        chain._entries[50] = tampered

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        assert result.first_invalid_sequence == 50

    def test_modify_timestamp(self):
        chain = _build_chain(100)
        original = chain[30]
        tampered_entry = replace(original.entry, timestamp=9999999999.0)
        tampered = ChainedEntry(
            entry=tampered_entry,
            previous_hash=original.previous_hash,
            current_hash=original.current_hash,
            sequence_number=original.sequence_number,
        )
        chain._entries[30] = tampered

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        assert result.first_invalid_sequence == 30


class TestTamperFirstEntry:
    """Modify the first entry in the chain."""

    def test_modify_genesis_entry(self):
        chain = _build_chain(100)
        original = chain[0]
        tampered_entry = replace(original.entry, domain="evil.example.com")
        tampered = ChainedEntry(
            entry=tampered_entry,
            previous_hash=original.previous_hash,
            current_hash=original.current_hash,
            sequence_number=0,
        )
        chain._entries[0] = tampered

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        assert result.first_invalid_sequence == 0


class TestDeleteEntry:
    """Remove an entry from the middle of the chain."""

    def test_delete_middle_entry(self):
        chain = _build_chain(100)
        # Remove entry 50 -- entries 51+ still reference entry 50's hash
        del chain._entries[50]
        # Fix sequence numbers so it looks like a gap
        # (in practice, the previous_hash chain is broken)

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        # The chain break is detected at the entry that now sits at position 50
        # because its previous_hash doesn't match the current_hash of position 49
        assert result.first_invalid_sequence == 50


class TestReorderEntries:
    """Swap two entries in the chain."""

    def test_swap_entries_10_and_11(self):
        chain = _build_chain(100)
        # Swap entries at positions 10 and 11
        chain._entries[10], chain._entries[11] = (
            chain._entries[11],
            chain._entries[10],
        )

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        # Detection happens at position 10 because the previous_hash
        # of what's now at position 10 doesn't match position 9's current_hash
        assert result.first_invalid_sequence == 10


class TestTamperWithHmac:
    """HMAC chain catches tampering the same way."""

    def test_hmac_tamper_detected(self):
        chain = _build_chain(100, use_hmac=True)
        original = chain[50]
        tampered_entry = replace(original.entry, domain="evil.example.com")
        tampered = ChainedEntry(
            entry=tampered_entry,
            previous_hash=original.previous_hash,
            current_hash=original.current_hash,
            sequence_number=original.sequence_number,
        )
        chain._entries[50] = tampered

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        assert result.first_invalid_sequence == 50

    def test_recomputed_sha256_fails_hmac_chain(self):
        """An attacker who recomputes SHA256 hashes can't forge an HMAC chain.

        This is the whole point of HMAC: without the secret key, you
        can't produce valid hashes even if you know the algorithm.
        """
        chain = _build_chain(10, use_hmac=True)

        # Tamper with entry 5 and try to recompute with SHA256 (no key)
        from chronoguard_lite.crypto.hasher import hash_entry

        original = chain[5]
        tampered_entry = replace(original.entry, domain="evil.example.com")
        # Recompute using plain SHA256 (attacker doesn't have the key)
        fake_hash = hash_entry(tampered_entry, original.previous_hash)
        tampered = ChainedEntry(
            entry=tampered_entry,
            previous_hash=original.previous_hash,
            current_hash=fake_hash,
            sequence_number=original.sequence_number,
        )
        chain._entries[5] = tampered

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        assert result.first_invalid_sequence == 5


class TestVerificationResultFields:
    """Verify the result object has useful debugging info."""

    def test_valid_result_fields(self):
        chain = _build_chain(10)
        result = ChainVerifier(chain).verify_full()
        assert result.is_valid
        assert result.entries_verified == 10
        assert result.first_invalid_sequence is None
        assert result.expected_hash is None
        assert result.actual_hash is None
        assert result.error_message is None

    def test_invalid_result_has_hashes(self):
        chain = _build_chain(10)
        original = chain[5]
        tampered_entry = replace(original.entry, domain="evil.example.com")
        tampered = ChainedEntry(
            entry=tampered_entry,
            previous_hash=original.previous_hash,
            current_hash=original.current_hash,
            sequence_number=original.sequence_number,
        )
        chain._entries[5] = tampered

        result = ChainVerifier(chain).verify_full()
        assert not result.is_valid
        assert result.expected_hash is not None
        assert result.actual_hash is not None
        assert len(result.expected_hash) == 64
        assert result.expected_hash != result.actual_hash
