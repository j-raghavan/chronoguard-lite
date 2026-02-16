# chronoguard-lite

A pure-Python agent compliance monitor — built chapter by chapter for
*Mastering Performant Code in Python, Volume 2*.

ChronoGuard Lite intercepts and logs every external request an AI agent makes,
enforces time-based access policies, maintains a tamper-proof audit trail, and
provides analytics — all in pure Python with zero infrastructure dependencies.

## Quick Start

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the project in development mode
uv sync --all-extras

# Verify CLI works
uv run chronoguard-lite --help

# Run tests
uv run pytest -v
```

## Project Structure

Each chapter of Volume 2 adds a module to this project:

| Chapter | Module | What It Builds |
|---------|--------|---------------|
| Ch1 | `domain/` | Agent, Policy, AuditEntry objects |
| Ch2 | `store/` | Time-series audit store with cache-friendly layout |
| Ch3 | `interceptor/` | Threaded request interceptor |
| Ch4 | `concurrency/` | Thread-safe policy cache + concurrent audit log |
| Ch5 | `interceptor/` | Async rewrite of the interceptor |
| Ch6 | `crypto/` | Cryptographic audit chain (SHA256, HMAC) |
| Ch7 | `analytics/` | HyperLogLog, Count-Min Sketch, Bloom filter |
| Ch8 | `strings/` | Domain pattern matching + full-text audit search |
| Ch9 | `graph/` | Policy dependency graph with topological evaluation |
| Ch10 | `profiling/` | Profile the whole system, find bottlenecks, optimize |

## Requirements

- Python 3.11+ (3.12 recommended)
- `uv` package manager

## License

MIT
