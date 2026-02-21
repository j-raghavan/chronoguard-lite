"""Tests for Bloom filter membership testing."""
from __future__ import annotations

import pytest

from chronoguard_lite.analytics.bloom import BloomFilter


class TestBloomBasics:
    def test_empty_filter(self):
        bf = BloomFilter(expected_elements=1000)
        assert not bf.might_contain("anything")
        assert bf.count == 0

    def test_add_and_check(self):
        bf = BloomFilter(expected_elements=1000)
        bf.add("agent-001:api.openai.com")
        assert bf.might_contain("agent-001:api.openai.com")

    def test_definitely_not_present(self):
        bf = BloomFilter(expected_elements=1000)
        bf.add("item-a")
        bf.add("item-b")
        # Not guaranteed, but with a properly sized filter and only
        # 2 items in a 1000-capacity filter, FP is vanishingly small
        assert not bf.might_contain("item-c")

    def test_no_false_negatives(self):
        """Every item that was added must return True."""
        bf = BloomFilter(expected_elements=10000, fp_rate=0.01)
        items = [f"item-{i}" for i in range(5000)]
        for item in items:
            bf.add(item)
        for item in items:
            assert bf.might_contain(item), f"False negative for {item}"

    def test_memory_size_scales(self):
        bf_small = BloomFilter(expected_elements=1000, fp_rate=0.01)
        bf_large = BloomFilter(expected_elements=1_000_000, fp_rate=0.01)
        assert bf_large.memory_bytes() > bf_small.memory_bytes()

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            BloomFilter(expected_elements=0)
        with pytest.raises(ValueError):
            BloomFilter(expected_elements=100, fp_rate=0.0)
        with pytest.raises(ValueError):
            BloomFilter(expected_elements=100, fp_rate=1.0)


class TestBloomFPRate:
    """Verify false positive rate stays near the target."""

    def test_fp_rate_at_capacity(self):
        """Fill the filter to its expected capacity and measure FP rate."""
        n = 10_000
        bf = BloomFilter(expected_elements=n, fp_rate=0.01)

        # Add n items
        for i in range(n):
            bf.add(f"item-{i}")

        # Test 10K items that were never added
        false_positives = 0
        test_count = 10_000
        for i in range(n, n + test_count):
            if bf.might_contain(f"item-{i}"):
                false_positives += 1

        fp_rate = false_positives / test_count
        print(f"\n  Bloom FP rate at capacity ({n}): {fp_rate:.4f} (target: 0.01)")
        print(f"  False positives: {false_positives} / {test_count}")
        print(f"  Fill ratio: {bf.fill_ratio():.4f}")
        print(f"  Estimated FP rate: {bf.estimated_fp_rate():.4f}")
        print(f"  Memory: {bf.memory_bytes():,} bytes")

        # Allow 3x the target rate (statistical variance)
        assert fp_rate < 0.03, f"FP rate {fp_rate:.4f} exceeds 3x target"

    def test_fp_rate_increases_beyond_capacity(self):
        """Overfilling the filter degrades FP rate."""
        n = 1000
        bf = BloomFilter(expected_elements=n, fp_rate=0.01)

        # Overfill by 5x
        for i in range(n * 5):
            bf.add(f"item-{i}")

        fp_before = bf.estimated_fp_rate()
        assert fp_before > 0.01  # should be worse than target
