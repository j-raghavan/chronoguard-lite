"""chronoguard-lite CLI entry point.

Usage: uv run chronoguard-lite [command]
"""
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chronoguard-lite",
        description="Agent compliance monitor — pure Python, zero infrastructure.",
    )
    _ = parser.add_subparsers(dest="command")

    # Each chapter registers its subcommand as it's built
    # Ch3/5: serve — start the interceptor
    # Ch6:   verify — verify audit chain integrity
    # Ch7:   analytics — run analytics queries
    # Ch8:   search — search audit logs
    # Ch9:   policy-check — evaluate policy graph
    # Ch10:  profile — run profiling harness

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)
