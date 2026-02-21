"""Report generation for profiling results.

Formats PipelineResult data into human-readable tables for the
chapter prose and for terminal output.
"""
from __future__ import annotations

from chronoguard_lite.profiling.harness import PipelineResult


def format_report(result: PipelineResult, label: str = "Pipeline") -> str:
    """Format a PipelineResult as a readable report string."""
    lines = [
        f"=== {label} ===",
        f"Requests:          {result.total_requests:,}",
        f"Total time:        {result.total_time_ms:.1f} ms",
        f"Throughput:        {result.requests_per_sec:,.0f} req/sec",
        f"",
        f"Breakdown:",
        f"  Evaluation:      {result.eval_time_ms:.1f} ms "
        f"({result.eval_time_ms / result.total_time_ms * 100:.1f}%)",
        f"  Chain append:    {result.chain_append_time_ms:.1f} ms "
        f"({result.chain_append_time_ms / result.total_time_ms * 100:.1f}%)",
        f"  Chain verify:    {result.chain_verify_time_ms:.1f} ms "
        f"({result.chain_verify_time_ms / result.total_time_ms * 100:.1f}%)",
        f"  Domain match:    {result.domain_match_time_ms:.1f} ms "
        f"({result.domain_match_time_ms / result.total_time_ms * 100:.1f}%)",
        f"  Chain entries:   {result.entries_in_chain:,}",
    ]
    return "\n".join(lines)


def format_comparison(
    before: PipelineResult,
    after: PipelineResult,
) -> str:
    """Format a before/after comparison table."""

    def _speedup(old: float, new: float) -> str:
        if new <= 0:
            return "inf"
        ratio = old / new
        return f"{ratio:.1f}x"

    lines = [
        f"{'Metric':<30} {'Before':>12} {'After':>12} {'Speedup':>10}",
        "-" * 66,
        f"{'Total time (ms)':<30} {before.total_time_ms:>12.1f} "
        f"{after.total_time_ms:>12.1f} "
        f"{_speedup(before.total_time_ms, after.total_time_ms):>10}",
        f"{'Throughput (req/sec)':<30} {before.requests_per_sec:>12,.0f} "
        f"{after.requests_per_sec:>12,.0f} "
        f"{_speedup(after.requests_per_sec, before.requests_per_sec):>10}",
        f"{'Evaluation (ms)':<30} {before.eval_time_ms:>12.1f} "
        f"{after.eval_time_ms:>12.1f} "
        f"{_speedup(before.eval_time_ms, after.eval_time_ms):>10}",
        f"{'Chain verify (ms)':<30} {before.chain_verify_time_ms:>12.1f} "
        f"{after.chain_verify_time_ms:>12.1f} "
        f"{_speedup(before.chain_verify_time_ms, after.chain_verify_time_ms):>10}",
        f"{'Chain append (ms)':<30} {before.chain_append_time_ms:>12.1f} "
        f"{after.chain_append_time_ms:>12.1f} "
        f"{_speedup(before.chain_append_time_ms, after.chain_append_time_ms):>10}",
        f"{'Domain match (ms)':<30} {before.domain_match_time_ms:>12.1f} "
        f"{after.domain_match_time_ms:>12.1f} "
        f"{_speedup(before.domain_match_time_ms, after.domain_match_time_ms):>10}",
    ]
    return "\n".join(lines)
