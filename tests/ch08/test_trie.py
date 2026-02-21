"""Tests for the DomainTrie."""

import pytest

from chronoguard_lite.strings.trie import DomainTrie


class TestTrieBasics:
    """Basic trie operations."""

    def test_empty_trie(self):
        t = DomainTrie()
        assert t.pattern_count == 0
        assert t.match("anything.com") == []

    def test_exact_match(self):
        t = DomainTrie()
        t.insert("api.openai.com")
        assert t.match("api.openai.com") == ["api.openai.com"]
        assert t.match("chat.openai.com") == []

    def test_wildcard_prefix(self):
        t = DomainTrie()
        t.insert("*.openai.com")
        assert t.match("api.openai.com") == ["*.openai.com"]
        assert t.match("chat.openai.com") == ["*.openai.com"]
        assert t.match("openai.com") == []  # fewer segments

    def test_wildcard_middle(self):
        t = DomainTrie()
        t.insert("api.*.internal")
        assert t.match("api.staging.internal") == ["api.*.internal"]
        assert t.match("api.prod.internal") == ["api.*.internal"]
        assert t.match("web.staging.internal") == []

    def test_multiple_wildcards(self):
        t = DomainTrie()
        t.insert("*.*.internal")
        assert t.match("api.staging.internal") == ["*.*.internal"]
        assert t.match("web.prod.internal") == ["*.*.internal"]
        assert t.match("internal") == []

    def test_multiple_patterns_match(self):
        t = DomainTrie()
        t.insert("*.openai.com")
        t.insert("api.openai.com")
        results = t.match("api.openai.com")
        assert sorted(results) == ["*.openai.com", "api.openai.com"]

    def test_no_partial_match(self):
        """Pattern with 3 segments should not match domain with 4."""
        t = DomainTrie()
        t.insert("*.openai.com")
        assert t.match("api.v2.openai.com") == []

    def test_pattern_count(self):
        t = DomainTrie()
        t.insert("*.openai.com")
        t.insert("api.stripe.com")
        t.insert("*.*.internal")
        assert t.pattern_count == 3

    def test_node_count(self):
        t = DomainTrie()
        t.insert("api.openai.com")
        # root -> com -> openai -> api = 4 nodes
        assert t.node_count() == 4

    def test_shared_suffix(self):
        """Two patterns sharing the same TLD and org should share trie nodes."""
        t = DomainTrie()
        t.insert("api.openai.com")
        t.insert("chat.openai.com")
        # root -> com -> openai -> api, chat = 5 nodes
        assert t.node_count() == 5


class TestTrieEdgeCases:
    """Edge cases and boundary conditions."""

    def test_single_segment_domain(self):
        t = DomainTrie()
        t.insert("localhost")
        assert t.match("localhost") == ["localhost"]
        assert t.match("other") == []

    def test_wildcard_only(self):
        t = DomainTrie()
        t.insert("*")
        assert t.match("anything") == ["*"]
        assert t.match("api.openai.com") == []  # 3 segments vs 1

    def test_many_patterns(self):
        t = DomainTrie()
        for i in range(1000):
            t.insert(f"api-{i}.example.com")
        assert t.match("api-500.example.com") == ["api-500.example.com"]
        assert t.match("api-9999.example.com") == []
        assert t.pattern_count == 1000
