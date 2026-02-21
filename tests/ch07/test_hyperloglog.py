"""Tests for HyperLogLog cardinality estimator."""
from __future__ import annotations

import pytest

from chronoguard_lite.analytics.hyperloglog import HyperLogLog


class TestHLLBasics:
    def test_empty(self):
        hll = HyperLogLog()
        assert hll.count() == 0

    def test_single_item(self):
        hll = HyperLogLog()
        hll.add("agent-001")
        assert hll.count() >= 1

    def test_duplicates_dont_increase_count(self):
        hll = HyperLogLog()
        for _ in range(1000):
            hll.add("same-item")
        assert hll.count() <= 3  # should be ~1, allow some noise

    def test_memory_size(self):
        hll = HyperLogLog(p=11)
        assert hll.memory_bytes() == 2048
        assert hll.num_registers == 2048

    def test_standard_error(self):
        hll = HyperLogLog(p=11)
        se = hll.standard_error()
        assert 0.02 < se < 0.03  # ~2.3%

    def test_invalid_precision(self):
        with pytest.raises(ValueError):
            HyperLogLog(p=2)
        with pytest.raises(ValueError):
            HyperLogLog(p=20)


class TestHLLAccuracy:
    """Verify error stays within theoretical bounds."""

    def test_100_items(self):
        hll = HyperLogLog(p=11)
        for i in range(100):
            hll.add(f"item-{i}")
        est = hll.count()
        # Allow 15% relative error for small cardinalities
        assert 70 <= est <= 130, f"Expected ~100, got {est}"

    def test_10k_items(self):
        hll = HyperLogLog(p=11)
        for i in range(10_000):
            hll.add(f"item-{i}")
        est = hll.count()
        # Standard error ~2.3%, allow 3x that (~7%)
        assert 9_000 <= est <= 11_000, f"Expected ~10000, got {est}"

    def test_100k_items(self):
        hll = HyperLogLog(p=11)
        for i in range(100_000):
            hll.add(f"item-{i}")
        est = hll.count()
        # Allow 5% relative error
        assert 95_000 <= est <= 105_000, f"Expected ~100000, got {est}"


class TestHLLMerge:
    def test_merge_disjoint(self):
        hll1 = HyperLogLog(p=11)
        hll2 = HyperLogLog(p=11)
        for i in range(5000):
            hll1.add(f"set-a-{i}")
        for i in range(5000):
            hll2.add(f"set-b-{i}")

        hll1.merge(hll2)
        est = hll1.count()
        assert 9_000 <= est <= 11_000, f"Expected ~10000, got {est}"

    def test_merge_overlapping(self):
        hll1 = HyperLogLog(p=11)
        hll2 = HyperLogLog(p=11)
        for i in range(5000):
            hll1.add(f"item-{i}")
        for i in range(3000, 8000):
            hll2.add(f"item-{i}")

        hll1.merge(hll2)
        # Union is items 0..7999 = 8000 unique
        est = hll1.count()
        assert 7_000 <= est <= 9_000, f"Expected ~8000, got {est}"

    def test_merge_different_precision_fails(self):
        hll1 = HyperLogLog(p=10)
        hll2 = HyperLogLog(p=11)
        with pytest.raises(ValueError):
            hll1.merge(hll2)
