"""Before/after benchmark tests for the profiling chapter.

These tests run the full pipeline in both unoptimized and optimized
modes and report the improvement.  The numbers feed directly into the
chapter prose.
"""
from __future__ import annotations

import time

from chronoguard_lite.profiling.harness import run_pipeline, run_pipeline_optimized
from chronoguard_lite.profiling.report import format_comparison, format_report


class TestBeforeAfterBenchmark:
    def test_10k_requests_comparison(self) -> None:
        """The main benchmark: 10K requests, before and after."""
        before = run_pipeline(
            total_requests=10_000,
            num_agents=50,
            num_policies=20,
            verify_every=1000,
        )
        after = run_pipeline_optimized(
            total_requests=10_000,
            num_agents=50,
            num_policies=20,
            verify_every=1000,
        )

        print(f"\n{format_report(before, 'Before (unoptimized)')}")
        print()
        print(f"{format_report(after, 'After (optimized)')}")
        print()
        print(format_comparison(before, after))

        # Optimized should be faster overall
        assert after.total_time_ms < before.total_time_ms
        # Verification should be dramatically faster
        assert after.chain_verify_time_ms < before.chain_verify_time_ms * 0.5
        # Evaluation should be faster (cache hits)
        assert after.eval_time_ms < before.eval_time_ms * 0.8

    def test_verification_scaling(self) -> None:
        """Show how verify_full() scales with chain length."""
        print("\nVerification scaling:")
        for n in [1000, 5000, 10000]:
            result = run_pipeline(
                total_requests=n,
                num_agents=10,
                num_policies=5,
                verify_every=n,  # verify once at the end
            )
            result_opt = run_pipeline_optimized(
                total_requests=n,
                num_agents=10,
                num_policies=5,
                verify_every=n,
            )
            print(
                f"  {n:>6} entries: "
                f"full verify={result.chain_verify_time_ms:.1f}ms, "
                f"checkpoint verify={result_opt.chain_verify_time_ms:.1f}ms"
            )

    def test_cprofile_output(self) -> None:
        """Run with cProfile and print top functions."""
        result = run_pipeline(
            total_requests=5000,
            num_agents=20,
            num_policies=10,
            verify_every=1000,
            profile=True,
        )
        print(f"\n--- cProfile top functions (5K requests) ---")
        print(result.cprofile_stats)

    def test_eval_cache_hit_rate(self) -> None:
        """Measure how many requests hit the eval cache."""
        # With 50 agents and 200 domains, there are 10K possible pairs.
        # With 10K requests from a Zipf distribution, many pairs repeat.
        before = run_pipeline(
            total_requests=10_000,
            num_agents=50,
            num_policies=20,
            num_domains=200,
        )
        after = run_pipeline_optimized(
            total_requests=10_000,
            num_agents=50,
            num_policies=20,
            num_domains=200,
        )
        speedup = before.eval_time_ms / after.eval_time_ms if after.eval_time_ms > 0 else 0
        print(f"\nEval cache effect:")
        print(f"  Before: {before.eval_time_ms:.1f}ms")
        print(f"  After:  {after.eval_time_ms:.1f}ms")
        print(f"  Speedup: {speedup:.1f}x")
        assert speedup > 1.5  # cache should help substantially
