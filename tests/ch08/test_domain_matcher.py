"""Tests for DomainMatcher (trie + AC + naive consistency)."""

import pytest

from chronoguard_lite.strings.domain_matcher import DomainMatcher


class TestDomainMatcherBasics:
    """Basic matching behavior."""

    def test_exact_match(self):
        m = DomainMatcher()
        m.add_pattern("api.openai.com")
        m.build()
        assert m.match("api.openai.com") == ["api.openai.com"]
        assert m.match("chat.openai.com") == []

    def test_wildcard_prefix(self):
        m = DomainMatcher()
        m.add_pattern("*.openai.com")
        m.build()
        assert m.match("api.openai.com") == ["*.openai.com"]
        assert m.match("chat.openai.com") == ["*.openai.com"]

    def test_wildcard_middle(self):
        m = DomainMatcher()
        m.add_pattern("api.*.internal")
        m.build()
        assert m.match("api.staging.internal") == ["api.*.internal"]

    def test_no_match(self):
        m = DomainMatcher()
        m.add_pattern("*.openai.com")
        m.build()
        assert m.match("google.com") == []

    def test_pattern_count(self):
        m = DomainMatcher()
        m.add_pattern("*.openai.com")
        m.add_pattern("api.stripe.com")
        assert m.pattern_count == 2


class TestTrieVsACConsistency:
    """Trie and Aho-Corasick should return the same results."""

    def test_consistency_simple(self):
        m = DomainMatcher()
        patterns = [
            "*.openai.com",
            "api.openai.com",
            "*.stripe.com",
            "api.*.internal",
            "*.*.corp.com",
        ]
        for p in patterns:
            m.add_pattern(p)
        m.build()

        test_domains = [
            "api.openai.com",
            "chat.openai.com",
            "api.stripe.com",
            "api.staging.internal",
            "web.prod.corp.com",
            "random.example.org",
        ]
        for domain in test_domains:
            trie_results = sorted(m.match(domain))
            ac_results = sorted(m.match_ac(domain))
            naive_results = sorted(m.match_naive(domain))
            assert trie_results == ac_results, (
                f"Trie vs AC mismatch for {domain}: "
                f"{trie_results} vs {ac_results}"
            )
            assert trie_results == naive_results, (
                f"Trie vs Naive mismatch for {domain}: "
                f"{trie_results} vs {naive_results}"
            )

    def test_consistency_1000_patterns(self):
        """All three methods agree across 1000 patterns and 100 domains."""
        m = DomainMatcher()
        # Generate patterns
        orgs = [f"org-{i}" for i in range(100)]
        for org in orgs:
            m.add_pattern(f"*.{org}.com")      # wildcard prefix
            m.add_pattern(f"api.{org}.com")     # exact
            m.add_pattern(f"*.{org}.internal")  # different TLD
        # Also some double-wildcard patterns
        for i in range(100):
            m.add_pattern(f"*.*.zone-{i}.net")
        # Some exact matches
        for i in range(500):
            m.add_pattern(f"host-{i}.example.com")
        m.build()

        test_domains = (
            [f"api.org-{i}.com" for i in range(100)]
            + [f"web.org-{i}.internal" for i in range(50)]
            + [f"host-{i}.example.com" for i in range(50)]
            + [f"a.b.zone-{i}.net" for i in range(20)]
            + ["no.match.here", "also.nothing.xyz"]
        )

        mismatches = []
        for domain in test_domains:
            trie = sorted(m.match(domain))
            ac = sorted(m.match_ac(domain))
            naive = sorted(m.match_naive(domain))
            if trie != naive:
                mismatches.append(f"Trie vs Naive: {domain}")
            if ac != naive:
                mismatches.append(f"AC vs Naive: {domain}")

        assert not mismatches, f"Mismatches found:\n" + "\n".join(mismatches)
