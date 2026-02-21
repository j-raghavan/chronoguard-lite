"""Tests for the Aho-Corasick automaton."""

import pytest

from chronoguard_lite.strings.aho_corasick import AhoCorasick


class TestACBasics:
    """Basic Aho-Corasick functionality."""

    def test_empty_automaton(self):
        ac = AhoCorasick()
        ac.build()
        assert ac.search("api.openai.com") == []

    def test_exact_match(self):
        ac = AhoCorasick()
        ac.add_pattern("api.openai.com")
        ac.build()
        assert ac.search("api.openai.com") == ["api.openai.com"]
        assert ac.search("chat.openai.com") == []

    def test_wildcard_prefix(self):
        ac = AhoCorasick()
        ac.add_pattern("*.openai.com")
        ac.build()
        assert ac.search("api.openai.com") == ["*.openai.com"]
        assert ac.search("chat.openai.com") == ["*.openai.com"]

    def test_wildcard_middle(self):
        ac = AhoCorasick()
        ac.add_pattern("api.*.internal")
        ac.build()
        assert ac.search("api.staging.internal") == ["api.*.internal"]
        assert ac.search("api.prod.internal") == ["api.*.internal"]
        assert ac.search("web.staging.internal") == []

    def test_multiple_patterns(self):
        ac = AhoCorasick()
        ac.add_pattern("*.openai.com")
        ac.add_pattern("api.openai.com")
        ac.build()
        results = sorted(ac.search("api.openai.com"))
        assert results == ["*.openai.com", "api.openai.com"]

    def test_no_match_different_length(self):
        ac = AhoCorasick()
        ac.add_pattern("*.openai.com")
        ac.build()
        assert ac.search("api.v2.openai.com") == []

    def test_must_build_before_search(self):
        ac = AhoCorasick()
        ac.add_pattern("test.com")
        with pytest.raises(RuntimeError, match="Must call build"):
            ac.search("test.com")

    def test_pattern_count(self):
        ac = AhoCorasick()
        ac.add_pattern("*.openai.com")
        ac.add_pattern("api.stripe.com")
        assert ac.pattern_count == 2


class TestACMultiPattern:
    """Multi-pattern matching scenarios."""

    def test_disjoint_patterns(self):
        ac = AhoCorasick()
        ac.add_pattern("api.openai.com")
        ac.add_pattern("api.stripe.com")
        ac.add_pattern("api.twilio.com")
        ac.build()
        assert ac.search("api.openai.com") == ["api.openai.com"]
        assert ac.search("api.stripe.com") == ["api.stripe.com"]
        assert ac.search("api.github.com") == []

    def test_overlapping_wildcards(self):
        ac = AhoCorasick()
        ac.add_pattern("*.openai.com")
        ac.add_pattern("*.*.com")
        ac.build()
        results = sorted(ac.search("api.openai.com"))
        assert results == ["*.*.com", "*.openai.com"]

    def test_many_patterns(self):
        ac = AhoCorasick()
        for i in range(500):
            ac.add_pattern(f"api-{i}.example.com")
        for i in range(500):
            ac.add_pattern(f"*.zone-{i}.internal")
        ac.build()
        assert ac.search("api-250.example.com") == ["api-250.example.com"]
        assert ac.search("web.zone-100.internal") == ["*.zone-100.internal"]
        assert ac.search("random.other.org") == []
        assert ac.pattern_count == 1000

    def test_wildcard_and_exact_same_structure(self):
        """Both *.x.com and api.x.com should match api.x.com."""
        ac = AhoCorasick()
        ac.add_pattern("*.stripe.com")
        ac.add_pattern("api.stripe.com")
        ac.build()
        results = sorted(ac.search("api.stripe.com"))
        assert results == ["*.stripe.com", "api.stripe.com"]
        # Only wildcard should match dashboard
        assert ac.search("dashboard.stripe.com") == ["*.stripe.com"]
