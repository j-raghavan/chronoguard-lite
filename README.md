# chronoguard-lite

**Companion repository for [Mastering Performant Code in Python, Volume 2](https://www.amazon.com/dp/9798249314798)**

A pure-Python agent compliance monitor built from scratch -- no Docker, no Redis, no infrastructure to wrangle. Every chapter adds a working module, benchmarks it against the naive version, and teaches you what Python is doing below the API surface.

ChronoGuard Lite intercepts and logs every external request an AI agent makes, enforces time-based access policies, maintains a tamper-proof audit chain, and provides real-time analytics.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/j-raghavan/chronoguard-lite.git
cd chronoguard-lite

# Install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --all-extras

# Verify everything works
uv run chronoguard-lite --help

# Run the full test suite
uv run pytest -v
```

## How to Use This Repo

The repo uses a **branch-per-chapter** strategy. Each branch builds on the previous one, adding the module that chapter covers.

To follow along with a chapter:

```bash
# Start Chapter 3
git checkout ch03

# Install deps and run tests
uv sync --all-extras
uv run pytest -v

# Run benchmarks for this chapter
uv run pytest -m benchmark -v
```

### Branch Map

| Branch | Chapter | What Gets Built | Tests |
|--------|---------|----------------|-------|
| `ch01` | Python's Memory Model | `domain/` -- Agent, Policy, AuditEntry objects | 5 |
| `ch02` | Cache-Aware Data Layout | `store/` -- Columnar audit store with bisect queries | 9 |
| `ch03` | The GIL Demystified | `interceptor/` -- Threaded request interceptor | 13 |
| `ch04` | Thread-Safe Data Structures | `concurrency/` -- Striped locks, concurrent audit log | 18 |
| `ch05` | The Async Rewrite | `interceptor/` -- async/await rewrite, no threads | 21 |
| `ch06` | Cryptographic Audit Chains | `crypto/` -- SHA-256 hash chain, HMAC verification | 26 |
| `ch07` | Probabilistic Data Structures | `analytics/` -- HyperLogLog, Count-Min Sketch, Bloom filter | 31 |
| `ch08` | String Processing at Scale | `strings/` -- Aho-Corasick domain matching, full-text search | 37 |
| `ch09` | Graph Algorithms | `graph/` -- Policy DAG with topological sort | 43 |
| `ch10` | Profiling and Optimization | `profiling/` -- End-to-end profiling, bottleneck fixes | 46 |
| `main` | Complete project | All modules integrated | 46 |

Each branch is cumulative. `ch05` contains everything from `ch01` through `ch05`.

## Project Structure

```
chronoguard-lite/
  src/chronoguard_lite/
    domain/         # Ch1: core data model (Agent, Policy, AuditEntry)
    store/          # Ch2: columnar audit store, bisect-based queries
    interceptor/    # Ch3/5: request interceptor (threaded, then async)
    concurrency/    # Ch4: striped lock map, concurrent audit log
    crypto/         # Ch6: SHA-256 hash chain, HMAC signing
    analytics/      # Ch7: HyperLogLog, Count-Min Sketch, Bloom filter
    strings/        # Ch8: Aho-Corasick matcher, full-text audit search
    graph/          # Ch9: policy dependency DAG, topological evaluator
    profiling/      # Ch10: pipeline profiler, optimization passes
    cli.py          # CLI entry point
  tests/            # 46 test files, one per module per chapter
  benchmarks/       # Micro-benchmarks referenced in the book
```

## Requirements

- **Python 3.10+** (3.12 recommended)
- **uv** package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))

Zero external dependencies for the core modules (Chapters 1-4, 6, 8-9). Optional dependencies:

- `aiohttp` for the async interceptor (Chapter 5)
- `py-spy`, `scalene`, `memray`, `line-profiler` for profiling (Chapter 10)

## Running Tests

```bash
# All tests
uv run pytest -v

# Just one chapter's tests
uv run pytest tests/ch03/ -v

# Benchmarks only
uv run pytest -m benchmark -v

# Skip slow tests
uv run pytest -m "not slow" -v
```

## About the Book

*Mastering Performant Code in Python, Volume 2: Concurrency, Memory, and the Algorithms Behind Fast Python*

By **Jayasimha Raghavan**

Available on [Amazon](https://www.amazon.com/dp/9798249314798) in paperback and Kindle.

Every external service from a production compliance monitor is replaced with a hand-built Python equivalent: Redis becomes an in-memory hash map, PostgreSQL becomes a columnar array with bisect queries, OPA becomes a DAG evaluator with topological sort. The point is to learn the algorithms behind the tools, not the tools themselves.

## License

MIT
