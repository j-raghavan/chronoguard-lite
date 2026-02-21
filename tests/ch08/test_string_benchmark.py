"""Benchmark tests for Chapter 8: domain matching and search performance."""

import random
import re
import sys
import time
import uuid

import pytest

from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.strings.domain_matcher import DomainMatcher
from chronoguard_lite.strings.search_engine import AuditSearchEngine

from tests.ch08.conftest import generate_entries, SEED

# ---------------------------------------------------------------------------
# Domain matching benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
class TestDomainMatchingBenchmark:
    """Compare trie, Aho-Corasick, and naive matching."""

    def _build_matcher(self, pattern_count: int) -> DomainMatcher:
        """Build a matcher with `pattern_count` wildcard patterns."""
        rng = random.Random(SEED)
        m = DomainMatcher()
        orgs = [f"org-{i}" for i in range(pattern_count // 3 + 1)]
        tlds = ["com", "net", "io", "dev", "internal"]

        added = 0
        # Wildcard prefix patterns
        for org in orgs:
            if added >= pattern_count:
                break
            tld = rng.choice(tlds)
            m.add_pattern(f"*.{org}.{tld}")
            added += 1
        # Exact patterns
        for org in orgs:
            if added >= pattern_count:
                break
            tld = rng.choice(tlds)
            m.add_pattern(f"api.{org}.{tld}")
            added += 1
        # Double-wildcard patterns
        for org in orgs:
            if added >= pattern_count:
                break
            tld = rng.choice(tlds)
            m.add_pattern(f"*.*.{org}.{tld}")
            added += 1

        m.build()
        return m

    def _generate_test_domains(self, count: int, pattern_count: int) -> list[str]:
        """Generate domains, some matching patterns, some not."""
        rng = random.Random(SEED + 1)
        domains = []
        tlds = ["com", "net", "io", "dev", "internal"]
        for i in range(count):
            org_idx = rng.randint(0, pattern_count // 3)
            prefix = rng.choice(["api", "web", "cdn", "staging", "prod"])
            tld = rng.choice(tlds)
            domains.append(f"{prefix}.org-{org_idx}.{tld}")
        return domains

    def test_trie_vs_naive_1000_patterns(self):
        """Trie vs naive at 1000 patterns, 10K domain lookups."""
        matcher = self._build_matcher(1000)
        domains = self._generate_test_domains(10_000, 1000)

        # Naive timing
        start = time.perf_counter()
        naive_results = [matcher.match_naive(d) for d in domains]
        naive_time = time.perf_counter() - start

        # Trie timing
        start = time.perf_counter()
        trie_results = [matcher.match(d) for d in domains]
        trie_time = time.perf_counter() - start

        # Correctness check
        for i, (n, t) in enumerate(zip(naive_results, trie_results)):
            assert sorted(n) == sorted(t), f"Mismatch at domain {domains[i]}"

        speedup = naive_time / trie_time if trie_time > 0 else float("inf")

        print(f"\n  Domain matching: 1000 patterns, 10K lookups")
        print(f"  Naive:  {naive_time:.4f}s ({naive_time/len(domains)*1e6:.1f} us/lookup)")
        print(f"  Trie:   {trie_time:.4f}s ({trie_time/len(domains)*1e6:.1f} us/lookup)")
        print(f"  Speedup: {speedup:.1f}x")

    def test_ac_vs_naive_1000_patterns(self):
        """Aho-Corasick vs naive at 1000 patterns, 10K domain lookups."""
        matcher = self._build_matcher(1000)
        domains = self._generate_test_domains(10_000, 1000)

        # Naive timing
        start = time.perf_counter()
        naive_results = [matcher.match_naive(d) for d in domains]
        naive_time = time.perf_counter() - start

        # AC timing
        start = time.perf_counter()
        ac_results = [matcher.match_ac(d) for d in domains]
        ac_time = time.perf_counter() - start

        # Correctness check
        for i, (n, a) in enumerate(zip(naive_results, ac_results)):
            assert sorted(n) == sorted(a), f"Mismatch at domain {domains[i]}"

        speedup = naive_time / ac_time if ac_time > 0 else float("inf")

        print(f"\n  Domain matching (AC): 1000 patterns, 10K lookups")
        print(f"  Naive:          {naive_time:.4f}s ({naive_time/len(domains)*1e6:.1f} us/lookup)")
        print(f"  Aho-Corasick:   {ac_time:.4f}s ({ac_time/len(domains)*1e6:.1f} us/lookup)")
        print(f"  Speedup: {speedup:.1f}x")

    def test_trie_vs_regex_1000_patterns(self):
        """Trie vs compiled regex at 1000 patterns."""
        matcher = self._build_matcher(1000)
        domains = self._generate_test_domains(10_000, 1000)

        # Build regex patterns from the matcher's patterns
        regexes = []
        for pat in matcher._patterns:
            # Convert wildcard pattern to regex: *.openai.com -> [^.]+\.openai\.com
            escaped = pat.replace(".", r"\.")
            escaped = escaped.replace(r"*\.", r"[^.]+\.")
            # Handle trailing wildcard
            escaped = escaped.replace(r"\.*", r"\.[^.]+")
            regexes.append(re.compile("^" + escaped + "$"))

        # Regex timing
        start = time.perf_counter()
        regex_results = []
        for d in domains:
            matches = [matcher._patterns[i] for i, rx in enumerate(regexes) if rx.match(d)]
            regex_results.append(matches)
        regex_time = time.perf_counter() - start

        # Trie timing
        start = time.perf_counter()
        trie_results = [matcher.match(d) for d in domains]
        trie_time = time.perf_counter() - start

        speedup = regex_time / trie_time if trie_time > 0 else float("inf")

        print(f"\n  Trie vs compiled regex: 1000 patterns, 10K lookups")
        print(f"  Regex:  {regex_time:.4f}s ({regex_time/len(domains)*1e6:.1f} us/lookup)")
        print(f"  Trie:   {trie_time:.4f}s ({trie_time/len(domains)*1e6:.1f} us/lookup)")
        print(f"  Speedup: {speedup:.1f}x")


# ---------------------------------------------------------------------------
# Search engine benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
class TestSearchBenchmark:
    """Compare inverted index vs naive linear scan."""

    def test_index_vs_naive_100k(self):
        """Inverted index vs naive scan at 100K entries."""
        entries = generate_entries(100_000)
        eng = AuditSearchEngine()
        for e in entries:
            eng.index_entry(e)

        queries = [
            "domain:openai AND decision:DENY",
            "domain:internal",
            "decision:ALLOW",
            "domain:api AND decision:DENY",
        ]

        print(f"\n  Search benchmark: 100K entries")
        for q in queries:
            # Indexed
            start = time.perf_counter()
            idx_result = eng.search(q)
            idx_time = time.perf_counter() - start

            # Naive
            start = time.perf_counter()
            naive_result = eng.naive_search(q)
            naive_time = time.perf_counter() - start

            assert idx_result == naive_result, f"Mismatch for '{q}'"

            speedup = naive_time / idx_time if idx_time > 0 else float("inf")
            print(f"  Query: '{q}'")
            print(f"    Naive:   {naive_time*1000:.2f} ms, hits={len(naive_result)}")
            print(f"    Indexed: {idx_time*1000:.4f} ms, hits={len(idx_result)}")
            print(f"    Speedup: {speedup:.0f}x")

    def test_index_build_time(self):
        """Measure index build time."""
        entries = generate_entries(100_000)
        eng = AuditSearchEngine()

        start = time.perf_counter()
        for e in entries:
            eng.index_entry(e)
        build_time = time.perf_counter() - start

        entries_per_sec = len(entries) / build_time

        print(f"\n  Index build: 100K entries")
        print(f"  Time:       {build_time:.3f}s")
        print(f"  Throughput: {entries_per_sec:,.0f} entries/sec")
        print(f"  Memory:     ~{eng._index.memory_estimate_bytes() / 1024:.0f} KB")

    def test_index_vs_naive_1m(self):
        """Inverted index vs naive scan at 1M entries."""
        entries = generate_entries(1_000_000)
        eng = AuditSearchEngine()
        for e in entries:
            eng.index_entry(e)

        q = "domain:openai AND decision:DENY"

        # Indexed
        start = time.perf_counter()
        idx_result = eng.search(q)
        idx_time = time.perf_counter() - start

        # Naive
        start = time.perf_counter()
        naive_result = eng.naive_search(q)
        naive_time = time.perf_counter() - start

        assert idx_result == naive_result

        speedup = naive_time / idx_time if idx_time > 0 else float("inf")
        print(f"\n  Search: 1M entries, query='{q}'")
        print(f"  Naive:   {naive_time*1000:.1f} ms, hits={len(naive_result)}")
        print(f"  Indexed: {idx_time*1000:.4f} ms, hits={len(idx_result)}")
        print(f"  Speedup: {speedup:.0f}x")
        print(f"  Memory:  ~{eng._index.memory_estimate_bytes() / (1024*1024):.1f} MB")
