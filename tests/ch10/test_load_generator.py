"""Tests for the load generator."""
from __future__ import annotations

from chronoguard_lite.profiling.load_generator import LoadGenerator


class TestLoadGenerator:
    def test_generates_correct_count(self) -> None:
        gen = LoadGenerator(total_requests=500, seed=42)
        requests = gen.generate()
        assert len(requests) == 500

    def test_agents_are_active(self) -> None:
        gen = LoadGenerator(num_agents=10, seed=42)
        for agent in gen.agents:
            assert agent.can_make_requests()

    def test_policies_are_active(self) -> None:
        gen = LoadGenerator(num_policies=10, seed=42)
        for policy in gen.policies:
            from chronoguard_lite.domain.policy import PolicyStatus
            assert policy.status == PolicyStatus.ACTIVE

    def test_zipf_distribution_is_skewed(self) -> None:
        """Top domains should get disproportionate traffic."""
        gen = LoadGenerator(
            num_domains=100, total_requests=10_000, seed=42
        )
        requests = gen.generate()
        from collections import Counter
        domain_counts = Counter(r.domain for r in requests)
        top_10 = domain_counts.most_common(10)
        top_10_total = sum(c for _, c in top_10)
        # top 10% of domains should get at least 40% of traffic
        assert top_10_total > 4000, f"Top 10 domains got only {top_10_total}"

    def test_policies_for_agent(self) -> None:
        gen = LoadGenerator(num_agents=10, num_policies=15, seed=42)
        for idx in range(10):
            pols = gen.policies_for_agent(idx)
            assert 2 <= len(pols) <= 8

    def test_deterministic_with_seed(self) -> None:
        gen1 = LoadGenerator(total_requests=100, seed=99)
        gen2 = LoadGenerator(total_requests=100, seed=99)
        r1 = gen1.generate()
        r2 = gen2.generate()
        # domains are deterministic (derived from seed); agent_ids use
        # uuid4() so they differ across instances, but the domain
        # sequence and agent index sequence should be identical.
        for a, b in zip(r1, r2):
            assert a.domain == b.domain
