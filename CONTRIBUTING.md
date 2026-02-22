# Contributing to chronoguard-lite

Thanks for your interest in the project! This repo is the companion code for
*Mastering Performant Code in Python, Volume 2*. Here's how you can help.

## Reporting Issues

Found a bug in the code or a mistake in the tests? Please open an issue with:

- Which chapter branch you're on (`git branch --show-current`)
- Python version (`python --version`)
- What you expected vs. what happened
- Steps to reproduce

## Branch Strategy

Each chapter has its own branch (`ch01` through `ch10`), and `main` has the
complete project. If your fix is chapter-specific, base your PR on that branch.
If it applies to the full project, base it on `main`.

## Running the Test Suite

```bash
uv sync --all-extras
uv run pytest -v
uv run ruff check src/ tests/
uv run mypy src/chronoguard_lite/ --ignore-missing-imports
```

All tests must pass, and `ruff` and `mypy` must be clean before submitting a PR.

## Style

- Follow the existing code style (enforced by `ruff`)
- Keep variable names short and domain-specific -- `dlq`, `chunk`, `payload`, not `processed_data`
- Tests go in `tests/chXX/` matching the chapter they belong to
- Benchmarks go in `benchmarks/`

## What We're Not Looking For

- Framework integrations (Django, FastAPI, etc.) -- the project is intentionally pure Python
- External database drivers -- Redis, PostgreSQL, etc. are replaced on purpose
- AI-generated PRs without measured benchmarks -- if you claim a speedup, show the numbers

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
