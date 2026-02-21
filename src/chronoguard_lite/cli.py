"""chronoguard-lite CLI entry point.

Usage: uv run chronoguard-lite [command]
"""
import argparse
import sys


def _add_profile_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "profile",
        help="Run the profiling harness on the full pipeline.",
    )
    p.add_argument(
        "--requests", type=int, default=10_000,
        help="Total requests to generate (default: 10000)",
    )
    p.add_argument(
        "--agents", type=int, default=50,
        help="Number of simulated agents (default: 50)",
    )
    p.add_argument(
        "--policies", type=int, default=20,
        help="Number of policies (default: 20)",
    )
    p.add_argument(
        "--domains", type=int, default=200,
        help="Number of target domains (default: 200)",
    )
    p.add_argument(
        "--verify-every", type=int, default=1000,
        help="Run chain verification every N requests (default: 1000)",
    )
    p.add_argument(
        "--seed", type=int, default=42,
        help="RNG seed for reproducible runs (default: 42)",
    )
    p.add_argument(
        "--cprofile", action="store_true",
        help="Enable cProfile and print top functions by cumulative time.",
    )
    p.add_argument(
        "--compare", action="store_true",
        help="Run both unoptimized and optimized pipelines and print comparison.",
    )


def _run_profile(args: argparse.Namespace) -> None:
    from chronoguard_lite.profiling.harness import run_pipeline, run_pipeline_optimized
    from chronoguard_lite.profiling.report import format_comparison, format_report

    common = dict(
        total_requests=args.requests,
        num_agents=args.agents,
        num_policies=args.policies,
        num_domains=args.domains,
        verify_every=args.verify_every,
        seed=args.seed,
    )

    if args.compare:
        before = run_pipeline(**common)
        after = run_pipeline_optimized(**common)
        print(format_report(before, label="Before (unoptimized)"))
        print()
        print(format_report(after, label="After (optimized)"))
        print()
        print(format_comparison(before, after))
    else:
        result = run_pipeline(**common, profile=args.cprofile)
        print(format_report(result))
        if result.cprofile_stats:
            print()
            print("--- cProfile top functions ---")
            print(result.cprofile_stats)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chronoguard-lite",
        description="Agent compliance monitor -- pure Python, zero infrastructure.",
    )
    subparsers = parser.add_subparsers(dest="command")

    _add_profile_parser(subparsers)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "profile":
        _run_profile(args)
