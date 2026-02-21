"""Tests for the AuditSearchEngine."""

import pytest

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.strings.search_engine import AuditSearchEngine, QueryParseError

from tests.ch08.conftest import make_entry, generate_entries


class TestSearchEngineBasics:
    """Basic search operations."""

    def test_empty_engine(self):
        eng = AuditSearchEngine()
        assert eng.entry_count == 0
        assert eng.search("domain:openai") == []

    def test_single_field_search(self):
        eng = AuditSearchEngine()
        eng.index_entry(make_entry(domain="api.openai.com", decision=AccessDecision.ALLOW))
        eng.index_entry(make_entry(domain="api.stripe.com", decision=AccessDecision.DENY))

        assert eng.search("domain:openai") == [0]
        assert eng.search("decision:DENY") == [1]

    def test_and_query(self):
        eng = AuditSearchEngine()
        eng.index_entry(make_entry(domain="api.openai.com", decision=AccessDecision.ALLOW))
        eng.index_entry(make_entry(domain="api.openai.com", decision=AccessDecision.DENY))
        eng.index_entry(make_entry(domain="api.stripe.com", decision=AccessDecision.DENY))

        result = eng.search("domain:openai AND decision:DENY")
        assert result == [1]

    def test_time_range_query(self):
        eng = AuditSearchEngine()
        eng.index_entry(make_entry(domain="api.openai.com", timestamp=1000.0))
        eng.index_entry(make_entry(domain="api.openai.com", timestamp=2000.0))
        eng.index_entry(make_entry(domain="api.openai.com", timestamp=3000.0))

        result = eng.search("domain:openai AND time:1500-2500")
        assert result == [1]

    def test_reason_search(self):
        eng = AuditSearchEngine()
        eng.index_entry(make_entry(reason="Rate limit exceeded for agent"))
        eng.index_entry(make_entry(reason="Policy matched: allow rule"))

        assert eng.search("reason:rate") == [0]
        assert eng.search("reason:policy") == [1]

    def test_search_entries_returns_objects(self):
        eng = AuditSearchEngine()
        e = make_entry(domain="api.openai.com")
        eng.index_entry(e)

        results = eng.search_entries("domain:openai")
        assert len(results) == 1
        assert results[0].domain == "api.openai.com"

    def test_parse_error_no_colon(self):
        eng = AuditSearchEngine()
        with pytest.raises(QueryParseError, match="field:value"):
            eng.search("domain openai")

    def test_parse_error_empty_field(self):
        eng = AuditSearchEngine()
        with pytest.raises(QueryParseError, match="Empty"):
            eng.search(":openai")


class TestSearchVsNaive:
    """Verify indexed search matches naive scan."""

    def test_consistency_10k(self):
        entries = generate_entries(10_000)
        eng = AuditSearchEngine()
        for e in entries:
            eng.index_entry(e)

        queries = [
            "domain:openai",
            "decision:DENY",
            "domain:openai AND decision:DENY",
            "domain:api AND decision:ALLOW",
            "domain:internal",
            "reason:rate",
        ]
        for q in queries:
            indexed = eng.search(q)
            naive = eng.naive_search(q)
            assert indexed == naive, (
                f"Mismatch for query '{q}': "
                f"indexed={len(indexed)} vs naive={len(naive)}"
            )
