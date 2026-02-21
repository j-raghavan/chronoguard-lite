"""Tests for the profiling harness."""
from __future__ import annotations

from chronoguard_lite.profiling.harness import run_pipeline, run_pipeline_optimized


class TestHarness:
    def test_pipeline_runs(self) -> None:
        result = run_pipeline(total_requests=100, num_agents=5, num_policies=5)
        assert result.total_requests == 100
        assert result.entries_in_chain == 100
        assert result.total_time_ms > 0
        assert result.requests_per_sec > 0

    def test_pipeline_with_profiling(self) -> None:
        result = run_pipeline(
            total_requests=100, num_agents=5, num_policies=5, profile=True
        )
        assert result.cprofile_stats is not None
        assert "function calls" in result.cprofile_stats

    def test_optimized_pipeline_runs(self) -> None:
        result = run_pipeline_optimized(
            total_requests=100, num_agents=5, num_policies=5
        )
        assert result.total_requests == 100
        assert result.entries_in_chain == 100

    def test_verification_happens(self) -> None:
        """With verify_every=50 and 200 requests, verification runs 4 times."""
        result = run_pipeline(
            total_requests=200, num_agents=5, num_policies=5,
            verify_every=50,
        )
        assert result.chain_verify_time_ms > 0

    def test_optimized_verification_faster(self) -> None:
        """Checkpoint verification should be faster than full verification."""
        before = run_pipeline(
            total_requests=2000, num_agents=10, num_policies=10,
            verify_every=500,
        )
        after = run_pipeline_optimized(
            total_requests=2000, num_agents=10, num_policies=10,
            verify_every=500,
        )
        # Optimized should have less verification time
        # (checkpoint only verifies new entries, not the full chain)
        assert after.chain_verify_time_ms < before.chain_verify_time_ms
