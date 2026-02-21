"""Tests for the InvertedIndex."""

import uuid
import pytest

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.strings.inverted_index import InvertedIndex

from tests.ch08.conftest import make_entry, generate_entries


class TestIndexBasics:
    """Basic index operations."""

    def test_empty_index(self):
        idx = InvertedIndex()
        assert idx.entry_count == 0
        assert idx.search_field("domain", "openai") == set()

    def test_index_single_entry(self):
        idx = InvertedIndex()
        entry = make_entry(domain="api.openai.com", decision=AccessDecision.ALLOW)
        idx.add_entry(entry)
        assert idx.entry_count == 1
        # Domain token search
        assert idx.search_field("domain", "openai") == {0}
        assert idx.search_field("domain", "api") == {0}
        assert idx.search_field("domain", "com") == {0}
        # Full domain search
        assert idx.search_field("domain", "api.openai.com") == {0}
        # Decision search
        assert idx.search_field("decision", "ALLOW") == {0}
        assert idx.search_field("decision", "DENY") == set()

    def test_index_multiple_entries(self):
        idx = InvertedIndex()
        idx.add_entry(make_entry(domain="api.openai.com", decision=AccessDecision.ALLOW))
        idx.add_entry(make_entry(domain="api.stripe.com", decision=AccessDecision.DENY))
        idx.add_entry(make_entry(domain="chat.openai.com", decision=AccessDecision.ALLOW))

        # "openai" appears in entries 0 and 2
        assert idx.search_field("domain", "openai") == {0, 2}
        # "api" appears in entries 0 and 1
        assert idx.search_field("domain", "api") == {0, 1}
        # DENY only in entry 1
        assert idx.search_field("decision", "DENY") == {1}

    def test_and_query(self):
        idx = InvertedIndex()
        idx.add_entry(make_entry(domain="api.openai.com", decision=AccessDecision.ALLOW))
        idx.add_entry(make_entry(domain="api.openai.com", decision=AccessDecision.DENY))
        idx.add_entry(make_entry(domain="api.stripe.com", decision=AccessDecision.DENY))

        # domain:openai AND decision:DENY -> only entry 1
        result = idx.search_and([("domain", "openai"), ("decision", "DENY")])
        assert result == {1}

    def test_and_query_empty_intersection(self):
        idx = InvertedIndex()
        idx.add_entry(make_entry(domain="api.openai.com", decision=AccessDecision.ALLOW))
        idx.add_entry(make_entry(domain="api.stripe.com", decision=AccessDecision.DENY))

        # domain:openai AND decision:DENY -> empty (openai is ALLOW)
        result = idx.search_and([("domain", "openai"), ("decision", "DENY")])
        assert result == set()

    def test_reason_tokenization(self):
        idx = InvertedIndex()
        idx.add_entry(make_entry(reason="Rate limit exceeded for agent"))
        idx.add_entry(make_entry(reason="Policy matched: allow rule"))

        assert idx.search_field("reason", "rate") == {0}
        assert idx.search_field("reason", "limit") == {0}
        assert idx.search_field("reason", "policy") == {1}

    def test_agent_id_search(self):
        agent = uuid.UUID(int=42)
        idx = InvertedIndex()
        idx.add_entry(make_entry(agent_id=agent))
        idx.add_entry(make_entry())  # different random agent

        result = idx.search_field("agent_id", str(agent))
        assert result == {0}

    def test_case_insensitive_domain(self):
        idx = InvertedIndex()
        idx.add_entry(make_entry(domain="API.OpenAI.COM"))
        assert idx.search_field("domain", "openai") == {0}
        assert idx.search_field("domain", "OPENAI") == {0}

    def test_time_range_search(self):
        idx = InvertedIndex()
        idx.add_entry(make_entry(timestamp=1000.0))
        idx.add_entry(make_entry(timestamp=2000.0))
        idx.add_entry(make_entry(timestamp=3000.0))

        assert idx.search_time_range(1500.0, 2500.0) == {1}
        assert idx.search_time_range(0.0, 5000.0) == {0, 1, 2}
        assert idx.search_time_range(4000.0, 5000.0) == set()


class TestIndexScale:
    """Verify index works at scale."""

    def test_10k_entries(self):
        entries = generate_entries(10_000)
        idx = InvertedIndex()
        for e in entries:
            idx.add_entry(e)
        assert idx.entry_count == 10_000

        # Should find entries with "openai" in domain
        openai_set = idx.search_field("domain", "openai")
        assert len(openai_set) > 0
        # Verify correctness
        for i in openai_set:
            assert "openai" in entries[i].domain.lower()

        # AND query
        deny_openai = idx.search_and([("domain", "openai"), ("decision", "DENY")])
        for i in deny_openai:
            assert "openai" in entries[i].domain.lower()
            assert entries[i].decision == AccessDecision.DENY

    def test_term_count(self):
        idx = InvertedIndex()
        idx.add_entry(make_entry(domain="api.openai.com"))
        idx.add_entry(make_entry(domain="api.stripe.com"))
        # domain terms: api, openai, com, stripe, api.openai.com, api.stripe.com
        assert idx.term_count("domain") == 6
