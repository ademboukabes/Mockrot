# Contributing to Mockrot

Thank you for your interest in contributing to **Mockrot**!

This guide explains our development workflow, coding standards, and how to submit pull requests.

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

---

## Development Setup

Mockrot uses [uv](https://github.com/astral-sh/uv) and [hatchling](https://hatch.pypa.io/) for fast, reproducible dependency management.

### Prerequisites

- Python 3.10, 3.11, 3.12, or 3.13
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`)
- Git

### Initializing the Environment

```bash
# Clone the repository
git clone https://github.com/ademboukabes/Mockrot.git
cd Mockrot

# Install all dependencies including development tools
uv sync
```

---

## Development Commands

All development tasks are executed via `uv run`:

```bash
# Format code
uv run ruff format .

# Check code formatting
uv run ruff format --check .

# Lint code
uv run ruff check .

# Strict type checking (must produce 0 errors)
uv run pyright

# Run test suite
uv run pytest

# Run tests with branch coverage (must maintain >= 90%)
uv run pytest --cov=mockrot --cov-branch

# Build package distributions (wheel and sdist)
uv build
```

### Pre-Commit Verification

Before submitting or pushing changes, ensure this one-liner succeeds:

```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest --cov=mockrot --cov-branch
```

---

## Coding Standards

- **Strict Typing:** All code must pass `pyright --strict` with zero errors. `# pyright: ignore` is only allowed when strictly necessary with an explanation comment on the same line.
- **Fail-Safe Guarantee:** Mockrot must never crash downstream test suites. All internal exceptions must be handled at the isolated boundary in `plugin.py`.
- **Zero Emojis:** Terminal output, reports, logs, and error messages must remain clean, professional, and emoji-free.
- **Memory-Only Inspection:** Never use blocking I/O (like `inspect.stack()`) in execution hooks. Use `sys._getframe()` to remain compatible with async frameworks like Starlette and AnyIO.

---

## Git Workflow & Conventional Commits

We follow the [Conventional Commits](https://www.conventionalcommits.org/) 1.0 specification:

```text
<type>(<scope>): <short summary in imperative mood, lowercase, no period>

<optional description explaining WHY this change was made>
```

- **Types:** `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`.
- **Scopes:** `plugin`, `interceptor`, `extractor`, `validator`, `reporter`, `models`, `config`, `deps`.

Example:
```text
feat(validator): detect zombie fields in mocked typeddict returns
fix(interceptor): replace inspect.stack with sys._getframe to prevent blocking io
```

### Branching

- Create short-lived feature or bugfix branches from `main`:
  `feat/<description>` or `fix/<description>`
- Rebase your branch onto `main` before submitting a PR:
  `git fetch origin && git rebase origin/main`

---

## Submitting Pull Requests

1. Open a Pull Request referencing any relevant issues.
2. Fill out the PR template with clear descriptions of what changed, why, and how you tested it.
3. Ensure CI passes on all Python versions (3.10 to 3.13) with coverage >= 90%.
