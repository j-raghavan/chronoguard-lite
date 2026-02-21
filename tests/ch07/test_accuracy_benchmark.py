"""Benchmark: exact vs probabilistic at scale.

These tests measure actual memory usage and error rates on this
hardware. The numbers printed here are what we use in the Chapter 7
prose. No fabricated numbers.
"""
from __future__ import annotations

import random
import sys
import time
import uuid

import pytest

from chronoguard_lite.analytics.bloom import BloomFilter
from chronoguard_lite.analytics.countmin import CountMinSketch
from chronoguard_lite.analytics.engine import AnalyticsEngine
from chronoguard_lite.analytics.hyperloglog import HyperLogLog


SEED = 42


@pytest.mark.benchmark
class TestHLLvExact:
    """HyperLogLog vs set() for cardinality."""

    def test_hll_vs_set_100k(self):
        """Compare HLL vs exact set for 100K unique items."""
        hll = HyperLogLog(p=11)
        exact = set()

        for i in range(100_000):
            item = f"agent-{i}"
            hll.add(item)
            exact.add(item)

        hll_count = hll.count()
        exact_count = len(exact)
        error = abs(hll_count - exact_count) / exact_count * 100

        exact_mem = sys.getsizeof(exact)
        # set.__sizeof__ doesn't include the string objects themselves
        # rough estimate: each string "agent-XXXXX" ~ 60 bytes + pointer
        exact_mem_full = exact_mem + len(exact) * 68
        hll_mem = hll.memory_bytes()

        print(f"\n  HLL vs set() at 100K unique items:")
        print(f"  Exact count:  {exact_count:,}")
        print(f"  HLL estimate: {hll_count:,}")
        print(f"  Error:        {error:.2f}%")
        print(f"  Exact memory: ~{exact_mem_full / 1024:.0f} KB")
        print(f"  HLL memory:   {hll_mem / 1024:.1f} KB")
        print(f"  Savings:      {exact_mem_full / hll_mem:.0f}x")

        assert error < 5.0  # well within 3-sigma

    def test_hll_vs_set_1m(self):
        """HLL vs set at 1M unique items."""
        hll = HyperLogLog(p=11)

        for i in range(1_000_000):
            hll.add(f"agent-{i}")

        hll_count = hll.count()
        error = abs(hll_count - 1_000_000) / 1_000_000 * 100
        hll_mem = hll.memory_bytes()

        print(f"\n  HLL at 1M unique items:")
        print(f"  Estimate: {hll_count:,}")
        print(f"  Error:    {error:.2f}%")
        print(f"  Memory:   {hll_mem / 1024:.1f} KB")

        assert error < 5.0


@pytest.mark.benchmark
class TestCMSvExact:
    """Count-Min Sketch vs Counter for frequency."""

    def test_cms_vs_counter_100k(self):
        """Compare CMS vs exact Counter for 100K events across 100 domains."""
        from collections import Counter
        rng = random.Random(SEED)

        cms = CountMinSketch(width=2048, depth=5)
        exact = Counter()

        domains = [f"domain-{i}.com" for i in range(100)]
        # Zipf-like distribution
        for _ in range(100_000):
            idx = int(rng.paretovariate(1.0)) % len(domains)
            domain = domains[idx]
            cms.add(domain)
            exact[domain] += 1

        # Measure error on top-10 domains
        top10 = exact.most_common(10)
        max_error_pct = 0.0
        for domain, true_count in top10:
            est = cms.estimate(domain)
            error_pct = (est - true_count) / true_count * 100
            if error_pct > max_error_pct:
                max_error_pct = error_pct

        exact_mem = sys.getsizeof(exact)
        cms_mem = cms.memory_bytes()

        print(f"\n  CMS vs Counter at 100K events, 100 domains:")
        print(f"  Top domain: {top10[0][0]} true={top10[0][1]:,} est={cms.estimate(top10[0][0]):,}")
        print(f"  Max overestimate (top-10): {max_error_pct:.2f}%")
        print(f"  Exact memory: ~{exact_mem:,} bytes")
        print(f"  CMS memory:   {cms_mem:,} bytes (fixed regardless of key count)")

        # CMS should never underestimate
        for domain, true_count in top10:
            assert cms.estimate(domain) >= true_count

    def test_cms_vs_counter_100k_10k_domains(self):
        """CMS vs Counter with 10K distinct domains -- shows memory crossover."""
        from collections import Counter
        rng = random.Random(SEED)

        cms = CountMinSketch(width=2048, depth=5)
        exact = Counter()

        # 10K distinct domains: Counter grows, CMS stays fixed
        for _ in range(100_000):
            domain = f"domain-{rng.randint(0, 9999)}.com"
            cms.add(domain)
            exact[domain] += 1

        top10 = exact.most_common(10)
        max_error_pct = 0.0
        for domain, true_count in top10:
            est = cms.estimate(domain)
            error_pct = (est - true_count) / true_count * 100
            if error_pct > max_error_pct:
                max_error_pct = error_pct

        exact_mem = sys.getsizeof(exact)
        cms_mem = cms.memory_bytes()

        print(f"\n  CMS vs Counter at 100K events, 10K distinct domains:")
        print(f"  Top domain: {top10[0][0]} true={top10[0][1]:,} est={cms.estimate(top10[0][0]):,}")
        print(f"  Max overestimate (top-10): {max_error_pct:.2f}%")
        print(f"  Exact memory: ~{exact_mem:,} bytes (grows with distinct keys)")
        print(f"  CMS memory:   {cms_mem:,} bytes (fixed)")
        print(f"  Savings:      {exact_mem / cms_mem:.1f}x")

        for domain, true_count in top10:
            assert cms.estimate(domain) >= true_count


@pytest.mark.benchmark
class TestBloomVExact:
    """Bloom filter vs set for membership."""

    def test_bloom_vs_set_100k(self):
        """Bloom filter vs set at 100K unique (agent, domain) pairs."""
        bf = BloomFilter(expected_elements=100_000, fp_rate=0.01)
        exact = set()

        # Generate 100K genuinely unique keys so we actually fill the filter
        for i in range(100_000):
            key = f"agent-{i // 200}:{i}"
            bf.add(key)
            exact.add(key)

        # Check: no false negatives
        for key in exact:
            assert bf.might_contain(key), f"False negative: {key}"

        # Measure FP rate
        false_positives = 0
        test_count = 10_000
        for i in range(test_count):
            fake_key = f"fake-agent-{i}:fake-domain-{i}.com"
            if bf.might_contain(fake_key):
                false_positives += 1

        fp_rate = false_positives / test_count
        exact_mem = sys.getsizeof(exact) + sum(sys.getsizeof(k) for k in list(exact)[:100]) / 100 * len(exact)
        bf_mem = bf.memory_bytes()

        print(f"\n  Bloom vs set() at {len(exact):,} unique pairs:")
        print(f"  False positive rate: {fp_rate:.4f} (target: 0.01)")
        print(f"  Fill ratio: {bf.fill_ratio():.4f}")
        print(f"  Exact memory: ~{exact_mem / 1024:.0f} KB")
        print(f"  Bloom memory: {bf_mem / 1024:.0f} KB")
        print(f"  Savings:      {exact_mem / bf_mem:.1f}x")

        assert fp_rate < 0.03


@pytest.mark.benchmark
class TestEngineThroughput:
    """Measure how fast the engine can process entries."""

    def test_engine_throughput_100k(self):
        """Process 100K entries through the full engine."""
        from .conftest import generate_entries

        entries = generate_entries(100_000)
        engine = AnalyticsEngine(
            bloom_expected=100_000,
            bloom_fp_rate=0.01,
        )

        start = time.perf_counter()
        for entry in entries:
            engine.process_entry(entry)
        elapsed = time.perf_counter() - start

        throughput = len(entries) / elapsed
        report = engine.memory_report()

        print(f"\n  AnalyticsEngine throughput:")
        print(f"  Processed: {len(entries):,} entries in {elapsed:.2f}s")
        print(f"  Throughput: {throughput:,.0f} entries/sec")
        print(f"  Memory report:")
        print(f"    HLL: {report['hyperloglog_bytes']:,} bytes ({report['hyperloglog_domains']} domains)")
        print(f"    CMS: {report['countmin_bytes']:,} bytes")
        print(f"    Bloom: {report['bloom_bytes']:,} bytes")
        print(f"    Total: {report['total_bytes']:,} bytes ({report['total_bytes']/1024:.0f} KB)")

        assert engine.entries_processed == 100_000

    def test_engine_accuracy_vs_exact(self):
        """Compare engine answers to exact answers for 50K entries."""
        from collections import Counter
        from .conftest import generate_entries

        entries = generate_entries(50_000)
        engine = AnalyticsEngine(bloom_expected=50_000)

        # Track exact answers
        exact_agents_per_domain: dict[str, set[str]] = {}
        exact_domain_freq: Counter = Counter()
        exact_pairs: set[str] = set()

        for entry in entries:
            engine.process_entry(entry)
            domain = entry.domain
            agent_str = str(entry.agent_id)

            if domain not in exact_agents_per_domain:
                exact_agents_per_domain[domain] = set()
            exact_agents_per_domain[domain].add(agent_str)
            exact_domain_freq[domain] += 1
            exact_pairs.add(f"{agent_str}:{domain}")

        # Check HLL accuracy for top domains
        print(f"\n  Engine accuracy at 50K entries:")
        top_domains = exact_domain_freq.most_common(5)
        for domain, freq in top_domains:
            exact_unique = len(exact_agents_per_domain[domain])
            hll_unique = engine.unique_agents(domain)
            cms_freq = engine.domain_frequency(domain)
            hll_err = abs(hll_unique - exact_unique) / max(exact_unique, 1) * 100
            cms_err = (cms_freq - freq) / freq * 100

            print(f"  {domain}:")
            print(f"    Unique agents: exact={exact_unique}, HLL={hll_unique}, error={hll_err:.1f}%")
            print(f"    Frequency: exact={freq}, CMS={cms_freq}, overestimate={cms_err:.1f}%")

            # CMS never underestimates
            assert cms_freq >= freq

        # Check Bloom: zero false negatives
        fn_count = 0
        for key in exact_pairs:
            parts = key.split(":", 1)
            if not engine.has_accessed(parts[0], parts[1]):
                fn_count += 1
        assert fn_count == 0, f"Bloom false negatives: {fn_count}"
        print(f"  Bloom: 0 false negatives across {len(exact_pairs)} pairs")
