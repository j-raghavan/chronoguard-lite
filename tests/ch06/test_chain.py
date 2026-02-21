"""Tests for the append-only audit hash chain."""
from __future__ import annotations

import uuid

from chronoguard_lite.crypto.chain import GENESIS_HASH, AuditChain, ChainedEntry
from chronoguard_lite.crypto.hasher import generate_secret_key

from .conftest import make_entry, generate_entries


class TestChainBasics:
    """Core chain operations: append, length, iteration."""

    def test_empty_chain(self):
        chain = AuditChain()
        assert len(chain) == 0
        assert chain.head_hash == GENESIS_HASH

    def test_append_single(self):
        chain = AuditChain()
        entry = make_entry(ts=1700000000.0)
        chained = chain.append(entry)

        assert isinstance(chained, ChainedEntry)
        assert chained.sequence_number == 0
        assert chained.previous_hash == GENESIS_HASH
        assert len(chained.current_hash) == 64
        assert chained.current_hash != GENESIS_HASH
        assert chain.head_hash == chained.current_hash
        assert len(chain) == 1

    def test_append_links_hashes(self):
        chain = AuditChain()
        e1 = chain.append(make_entry(ts=1.0))
        e2 = chain.append(make_entry(ts=2.0))

        assert e2.previous_hash == e1.current_hash
        assert e2.current_hash != e1.current_hash
        assert e2.sequence_number == 1

    def test_append_1000_entries(self):
        chain = AuditChain()
        entries = generate_entries(1000)
        for entry in entries:
            chain.append(entry)

        assert len(chain) == 1000
        # Each entry links to its predecessor
        for i in range(1, 1000):
            assert chain[i].previous_hash == chain[i - 1].current_hash

    def test_iteration(self):
        chain = AuditChain()
        for i in range(5):
            chain.append(make_entry(ts=float(i)))

        items = list(chain)
        assert len(items) == 5
        assert all(isinstance(item, ChainedEntry) for item in items)
        assert [item.sequence_number for item in items] == [0, 1, 2, 3, 4]

    def test_get_by_sequence(self):
        chain = AuditChain()
        chain.append(make_entry(ts=1.0))
        chain.append(make_entry(ts=2.0))
        chain.append(make_entry(ts=3.0))

        assert chain.get(0).sequence_number == 0
        assert chain.get(2).sequence_number == 2

    def test_get_out_of_range(self):
        chain = AuditChain()
        chain.append(make_entry(ts=1.0))

        import pytest
        with pytest.raises(IndexError):
            chain.get(5)
        with pytest.raises(IndexError):
            chain.get(-1)

    def test_getitem(self):
        chain = AuditChain()
        chain.append(make_entry(ts=1.0))
        chain.append(make_entry(ts=2.0))
        assert chain[0].sequence_number == 0
        assert chain[1].sequence_number == 1


class TestChainWithHmac:
    """HMAC-SHA256 chain mode."""

    def test_with_hmac_generates_key(self):
        chain = AuditChain.with_hmac()
        assert chain.secret_key is not None
        assert len(chain.secret_key) == 32

    def test_with_hmac_uses_provided_key(self):
        key = b"my-secret-key-is-32-bytes-long!!"
        chain = AuditChain.with_hmac(secret_key=key)
        assert chain.secret_key == key

    def test_hmac_chain_links(self):
        chain = AuditChain.with_hmac()
        e1 = chain.append(make_entry(ts=1.0))
        e2 = chain.append(make_entry(ts=2.0))

        assert e2.previous_hash == e1.current_hash
        assert e1.previous_hash == GENESIS_HASH

    def test_different_keys_different_chains(self):
        """Same entries with different keys produce different hashes."""
        entry = make_entry(ts=1.0, agent_id=uuid.UUID(int=1), domain="test.com")

        chain1 = AuditChain.with_hmac(secret_key=b"key-one-is-thirty-two-bytes-long")
        chain2 = AuditChain.with_hmac(secret_key=b"key-two-is-thirty-two-bytes-long")

        # We need identical entries, so use the same object
        c1 = chain1.append(entry)
        c2 = chain2.append(entry)

        assert c1.current_hash != c2.current_hash

    def test_sha256_vs_hmac_different_hashes(self):
        """Plain SHA256 chain and HMAC chain produce different hashes."""
        entry = make_entry(ts=1.0, agent_id=uuid.UUID(int=1), domain="test.com")

        plain = AuditChain()
        hmac_chain = AuditChain.with_hmac(secret_key=b"a" * 32)

        p = plain.append(entry)
        h = hmac_chain.append(entry)

        assert p.current_hash != h.current_hash


class TestChainedEntryFields:
    """Verify ChainedEntry preserves the original AuditEntry."""

    def test_entry_preserved(self):
        chain = AuditChain()
        original = make_entry(
            ts=1700000000.0,
            domain="api.openai.com",
            decision="ALLOW",
        )
        # Note: make_entry uses AccessDecision enum, not string.
        # The point is the entry comes back unchanged.
        original = make_entry(ts=1700000000.0, domain="api.openai.com")
        chained = chain.append(original)

        assert chained.entry is original
        assert chained.entry.domain == "api.openai.com"
        assert chained.entry.timestamp == 1700000000.0
