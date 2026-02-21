"""Tests for the chain verifier."""
from __future__ import annotations

import pytest

from chronoguard_lite.crypto.chain import AuditChain
from chronoguard_lite.crypto.verifier import ChainVerifier

from .conftest import make_entry, generate_entries


class TestVerifyFull:
    """Full chain verification from genesis."""

    def test_empty_chain(self):
        chain = AuditChain()
        result = ChainVerifier(chain).verify_full()
        assert result.is_valid
        assert result.entries_verified == 0

    def test_single_entry(self):
        chain = AuditChain()
        chain.append(make_entry(ts=1.0))
        result = ChainVerifier(chain).verify_full()
        assert result.is_valid
        assert result.entries_verified == 1

    def test_1000_entries(self):
        chain = AuditChain()
        for entry in generate_entries(1000):
            chain.append(entry)
        result = ChainVerifier(chain).verify_full()
        assert result.is_valid
        assert result.entries_verified == 1000

    def test_hmac_chain_verifies(self):
        chain = AuditChain.with_hmac(secret_key=b"a" * 32)
        for entry in generate_entries(100):
            chain.append(entry)
        result = ChainVerifier(chain).verify_full()
        assert result.is_valid
        assert result.entries_verified == 100


class TestVerifyRange:
    """Range verification for subsets of the chain."""

    def test_verify_first_half(self):
        chain = AuditChain()
        for entry in generate_entries(100):
            chain.append(entry)
        result = ChainVerifier(chain).verify_range(0, 50)
        assert result.is_valid
        assert result.entries_verified == 50

    def test_verify_second_half(self):
        chain = AuditChain()
        for entry in generate_entries(100):
            chain.append(entry)
        result = ChainVerifier(chain).verify_range(50, 100)
        assert result.is_valid
        assert result.entries_verified == 50

    def test_verify_single_entry_range(self):
        chain = AuditChain()
        for entry in generate_entries(10):
            chain.append(entry)
        result = ChainVerifier(chain).verify_range(5, 6)
        assert result.is_valid
        assert result.entries_verified == 1

    def test_invalid_range_raises(self):
        chain = AuditChain()
        for entry in generate_entries(10):
            chain.append(entry)

        with pytest.raises(ValueError):
            ChainVerifier(chain).verify_range(-1, 5)
        with pytest.raises(ValueError):
            ChainVerifier(chain).verify_range(0, 20)
        with pytest.raises(ValueError):
            ChainVerifier(chain).verify_range(5, 3)


class TestVerifyEntry:
    """Single entry verification."""

    def test_verify_single(self):
        chain = AuditChain()
        for entry in generate_entries(10):
            chain.append(entry)
        result = ChainVerifier(chain).verify_entry(5)
        assert result.is_valid
        assert result.entries_verified == 1

    def test_verify_first_entry(self):
        chain = AuditChain()
        chain.append(make_entry(ts=1.0))
        result = ChainVerifier(chain).verify_entry(0)
        assert result.is_valid

    def test_verify_out_of_range(self):
        chain = AuditChain()
        chain.append(make_entry(ts=1.0))
        with pytest.raises(IndexError):
            ChainVerifier(chain).verify_entry(5)
