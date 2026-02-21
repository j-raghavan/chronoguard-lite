"""Tests for SHA256 and HMAC-SHA256 hashing of audit entries."""
from __future__ import annotations

import uuid
from dataclasses import replace

from chronoguard_lite.crypto.hasher import (
    generate_secret_key,
    hash_entry,
    hmac_entry,
)
from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision

from .conftest import make_entry


def _fixed_entry() -> AuditEntry:
    """An entry with every field pinned for deterministic tests."""
    return AuditEntry(
        entry_id=uuid.UUID(int=1),
        agent_id=uuid.UUID(int=2),
        domain="api.openai.com",
        decision=AccessDecision.ALLOW,
        timestamp=1700000000.0,
        reason="policy matched",
        policy_id=uuid.UUID(int=3),
        rule_id=uuid.UUID(int=4),
        request_method="GET",
        request_path="/v1/chat",
        source_ip="10.0.0.1",
        processing_time_ms=1.5,
    )


PREV_HASH = "a" * 64


class TestHashDeterministic:
    """Same inputs must always produce the same hash."""

    def test_sha256_deterministic(self):
        entry = _fixed_entry()
        h1 = hash_entry(entry, PREV_HASH)
        h2 = hash_entry(entry, PREV_HASH)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex digest

    def test_hmac_deterministic(self):
        entry = _fixed_entry()
        key = b"test-key-32-bytes-long-exactly!!"
        h1 = hmac_entry(entry, PREV_HASH, key)
        h2 = hmac_entry(entry, PREV_HASH, key)
        assert h1 == h2
        assert len(h1) == 64

    def test_sha256_and_hmac_differ(self):
        """Plain SHA256 and HMAC-SHA256 must produce different hashes."""
        entry = _fixed_entry()
        key = b"test-key-32-bytes-long-exactly!!"
        sha = hash_entry(entry, PREV_HASH)
        mac = hmac_entry(entry, PREV_HASH, key)
        assert sha != mac


class TestHashChangesWithField:
    """Changing any single field must change the hash (avalanche)."""

    def test_change_domain(self):
        base = _fixed_entry()
        modified = replace(base, domain="api.anthropic.com")
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_decision(self):
        base = _fixed_entry()
        modified = replace(base, decision=AccessDecision.DENY)
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_timestamp(self):
        base = _fixed_entry()
        modified = replace(base, timestamp=1700000001.0)
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_agent_id(self):
        base = _fixed_entry()
        modified = replace(base, agent_id=uuid.UUID(int=99))
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_entry_id(self):
        base = _fixed_entry()
        modified = replace(base, entry_id=uuid.UUID(int=99))
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_reason(self):
        base = _fixed_entry()
        modified = replace(base, reason="different reason")
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_policy_id(self):
        base = _fixed_entry()
        modified = replace(base, policy_id=uuid.UUID(int=99))
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_policy_id_to_none(self):
        base = _fixed_entry()
        modified = replace(base, policy_id=None)
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_rule_id(self):
        base = _fixed_entry()
        modified = replace(base, rule_id=uuid.UUID(int=99))
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_method(self):
        base = _fixed_entry()
        modified = replace(base, request_method="POST")
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_path(self):
        base = _fixed_entry()
        modified = replace(base, request_path="/v1/embeddings")
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_source_ip(self):
        base = _fixed_entry()
        modified = replace(base, source_ip="10.0.0.2")
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_latency(self):
        base = _fixed_entry()
        modified = replace(base, processing_time_ms=99.9)
        assert hash_entry(base, PREV_HASH) != hash_entry(modified, PREV_HASH)

    def test_change_previous_hash(self):
        """Different chain position = different hash."""
        entry = _fixed_entry()
        h1 = hash_entry(entry, "a" * 64)
        h2 = hash_entry(entry, "b" * 64)
        assert h1 != h2


class TestHmacRequiresKey:
    """Different keys must produce different hashes."""

    def test_different_keys_different_hashes(self):
        entry = _fixed_entry()
        key1 = b"key-one-is-thirty-two-bytes-long"
        key2 = b"key-two-is-thirty-two-bytes-long"
        h1 = hmac_entry(entry, PREV_HASH, key1)
        h2 = hmac_entry(entry, PREV_HASH, key2)
        assert h1 != h2

    def test_generate_secret_key_length(self):
        key = generate_secret_key()
        assert len(key) == 32
        assert isinstance(key, bytes)

    def test_generate_secret_key_unique(self):
        """Two generated keys should differ (with overwhelming probability)."""
        k1 = generate_secret_key()
        k2 = generate_secret_key()
        assert k1 != k2
