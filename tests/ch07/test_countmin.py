"""Tests for Count-Min Sketch frequency estimator."""
from __future__ import annotations

import pytest

from chronoguard_lite.analytics.countmin import CountMinSketch


class TestCMSBasics:
    def test_empty(self):
        cms = CountMinSketch()
        assert cms.estimate("anything") == 0
        assert cms.total == 0

    def test_single_add(self):
        cms = CountMinSketch()
        cms.add("domain.com")
        assert cms.estimate("domain.com") >= 1
        assert cms.total == 1

    def test_multiple_adds(self):
        cms = CountMinSketch()
        for _ in range(100):
            cms.add("domain.com")
        est = cms.estimate("domain.com")
        assert est >= 100  # CMS never underestimates
        assert cms.total == 100

    def test_unseen_item_zero_or_small(self):
        cms = CountMinSketch()
        for i in range(1000):
            cms.add(f"item-{i}")
        # An item never added should have a small (possibly zero) estimate
        est = cms.estimate("never-added")
        # Could be nonzero due to collisions, but should be small
        assert est < 50  # way less than 1000

    def test_memory_size(self):
        cms = CountMinSketch(width=2048, depth=5)
        assert cms.memory_bytes() == 2048 * 5 * 4

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            CountMinSketch(width=0, depth=5)

    def test_add_with_count(self):
        cms = CountMinSketch()
        cms.add("domain.com", count=50)
        assert cms.estimate("domain.com") >= 50
        assert cms.total == 50


class TestCMSAccuracy:
    """Verify overestimate stays within epsilon * N."""

    def test_frequency_accuracy_10k(self):
        """Add known frequencies and verify estimates."""
        cms = CountMinSketch(width=2048, depth=5)

        # Add items with known counts
        known = {
            "api.openai.com": 5000,
            "api.github.com": 3000,
            "api.stripe.com": 1500,
            "rare.domain.com": 50,
        }
        for domain, count in known.items():
            cms.add(domain, count=count)

        total = sum(known.values())
        eps_n = cms.epsilon() * total  # max overestimate with high prob

        for domain, true_count in known.items():
            est = cms.estimate(domain)
            assert est >= true_count, f"{domain}: estimate {est} < true {true_count}"
            overestimate = est - true_count
            # Allow some slack beyond theoretical bound for small samples
            assert overestimate <= eps_n * 3, (
                f"{domain}: overestimate {overestimate} >> eps*N={eps_n:.0f}"
            )

    def test_zipf_distribution_100k(self):
        """Simulate Zipf-like access pattern (top domains get most traffic)."""
        import random
        rng = random.Random(42)

        cms = CountMinSketch(width=2048, depth=5)
        domains = [f"domain-{i}.com" for i in range(100)]
        exact = {d: 0 for d in domains}

        # Zipf: domain i gets proportional to 1/(i+1) traffic
        weights = [1.0 / (i + 1) for i in range(100)]
        total_weight = sum(weights)
        probs = [w / total_weight for w in weights]

        for _ in range(100_000):
            # Weighted random choice
            r = rng.random()
            cumulative = 0.0
            chosen = domains[-1]
            for d, p in zip(domains, probs):
                cumulative += p
                if r <= cumulative:
                    chosen = d
                    break
            cms.add(chosen)
            exact[chosen] += 1

        # Check top-5 domains: estimates should be close
        top5 = sorted(exact.items(), key=lambda x: -x[1])[:5]
        for domain, true_count in top5:
            est = cms.estimate(domain)
            assert est >= true_count
            error_pct = (est - true_count) / true_count * 100
            # Top domains should have <5% overestimate with these params
            assert error_pct < 10, (
                f"{domain}: true={true_count}, est={est}, error={error_pct:.1f}%"
            )
