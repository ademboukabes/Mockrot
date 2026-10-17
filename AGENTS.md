# AGENTS.md — Mockrot

> **Single Source of Truth** for all AI agents (Claude Code, Antigravity, Cursor, Codex, Windsurf)
> and human contributors. The full historical product specification is located at
> [`docs/spec/v1-specification.md`](./docs/spec/v1-specification.md). This document defines
> **how** we work; the specification defines **what** to build.
>
> **Golden Rule:** In case of ambiguity, contradiction, or structural decisions not covered here,
> **stop and ask** rather than assume.

---

## 1. Project Context & Philosophy

**Mockrot** (`pytest-mockrot`) is a pytest plugin designed to detect **rotting mocks**: test mocks
whose call arguments or return values have drifted away from the actual production contract
(function signature and return type annotations).

- **The Problem:** `unittest.mock` (even with `autospec=True`) never verifies that `return_value`
  matches the annotated return type `-> ReturnType` of the real function. Test suites remain green
  on frozen, obsolete fake data for months until production breaks with `AttributeError`, `KeyError`,
  or `ValidationError`.
- **The Solution:** Intercept every mock, extract the runtime contract of the real underlying target
  (`inspect.signature` + `typing.get_type_hints`), and validate **both inputs and outputs** on every
  call using `pydantic.TypeAdapter`.
- **Product Promise:** Zero configuration (`pytest --mockrot`), zero noisy false positives,
  negligible overhead, and never crashes the user's test suite.
- **Target Audience:** Modern Python 3.10+ typed codebases (Pydantic, dataclasses, TypedDict) and an
  essential safety rail for AI-generated or AI-refactored code.

### Scope

| Version | Requirements | Deliverables |
| :--- | :--- | :--- |
| **V1 (MVP)** | F1 → F8 | Interception, signature validation, return validation, async support, `side_effect`, zombie fields, `warn`/`strict` modes, exclusions |
| **V1.1** | F9 → F12 | Record mode (`.mockrot.lock`), HTTP/OpenAPI mocks, LibCST auto-fixer, GitHub Action/JSON export |

**Never implement a V1.1 requirement before V1 is fully completed and verified**, unless explicitly
requested.

---

## 2. Technical Stack

| Role | Tool | Constraint |
| :--- | :--- | :--- |
| Language | Python | `>= 3.10` (CI matrix: 3.10 → 3.13) |
| Project & Build | `uv` + `hatchling` | `pyproject.toml` PEP 621, `src-layout`, locked `uv.lock` |
| Test Framework | `pytest` | `>= 8.0`, entry point `pytest11` |
| Contract Validation | `pydantic` v2 | `TypeAdapter` only, never use deprecated v1 APIs |
| Terminal Reporter | `rich` | Restricted exclusively to `reporter.py` |
| Auto-Fixer | `libcst` | Optional extra `pytest-mockrot[fix]` (heavy dependency) |
| Linting & Formatting | `ruff` | Zero warnings allowed |
| Type Checking | `pyright` in **strict** mode | Zero errors allowed |
| Test Suite | `pytest`, `pytester`, `pytest-cov`, `pytest-mock` | Code coverage ≥ 90% (lines + branches) |

- Distribution name: `pytest-mockrot` — importable module: `mockrot`.
- **No new runtime dependencies** without written justification and explicit approval. Every runtime
  dependency incurs an overhead cost for all downstream users.

---

## 3. Architecture

### Processing Pipeline

```text
pytest ──▶ plugin.py ──▶ interceptor.py ──▶ extractor.py ──▶ validator.py ──▶ reporter.py
           (hooks)       (mock capture)     (contract)       (violations)     (terminal/export)
```

### Module Responsibilities and Import Boundaries

| Module | Responsibility | Allowed Imports |
| :--- | :--- | :--- |
| `plugin.py` | Pytest hooks, CLI flags, `[tool.mockrot]` config, **sole fail-safe boundary** | Any project module |
| `interceptor.py` | Patching `unittest.mock._patch` and `MonkeyPatch.setattr`, call proxy | `extractor`, `validator`, `models` |
| `extractor.py` | Signature extraction, type hints, `ForwardRef`/`TYPE_CHECKING` resolution, async checks, contract cache | `models` |
| `validator.py` | Validation of arguments and return values, zombie field detection | `extractor`, `models` |
| `reporter.py` | Rich console rendering, JSON / SARIF / GitHub annotations export | `models` |
| `recorder.py` | Contract snapshot recording for `.mockrot.lock` (V1.1) | `models` |
| `fixer.py` | LibCST mock rewrite engine (V1.1) | `models` |
| `models.py` | Domain models (`Contract`, `Violation`, `MockSite`…) using `@dataclass(frozen=True, slots=True)` | Standard library only |

Rules:

- **Only `plugin.py` imports `pytest`.** The core engine (`extractor`, `validator`) must remain
  testable without pytest.
- **Only `reporter.py` imports `rich`.** Only `fixer.py` imports `libcst`.
- **Only `interceptor.py` accesses private internals** (`unittest.mock._patch`). Any dependency on
  private runtime APIs must be isolated, documented, and tested across Python 3.10 through 3.13.
- Modules communicate exclusively through strongly-typed domain objects in `models.py`, never via
  untyped `dict` or ad-hoc tuples.
- No circular imports. No mutable global state, except the session registry managed exclusively by
  `plugin.py`.

### Repository Structure

```text
mockrot/
├── pyproject.toml
├── uv.lock
├── AGENTS.md / CLAUDE.md / README.md / CHANGELOG.md / LICENSE
├── .github/workflows/ci.yml
├── docs/spec/v1-specification.md
├── src/mockrot/
│   ├── __init__.py  plugin.py  interceptor.py  extractor.py
│   ├── validator.py  reporter.py  models.py  errors.py  cli.py
│   ├── recorder.py  fixer.py          # V1.1
│   └── py.typed
└── tests/
    ├── unit/            # Pure engine tests, executed without pytest plugin hooks
    ├── integration/     # End-to-end plugin tests using pytester fixture
    └── fixtures/        # Mock production modules (sync, async, pydantic, dataclasses, TypedDict)
```

---

## 4. Non-Negotiable Product Invariants

1. **Never crash the user's test suite.** Any unexpected internal error must be caught at the
   **single fail-safe boundary** in `plugin.py`, converted into a warning or degraded mode notice,
   allowing the underlying test to run normally.
2. **Total behavioral transparency.** The proxy wrapper must never alter the returned value,
   raise an unexpected exception, or distort the mock's behavior. In `warn` mode, tests must behave
   identically with or without Mockrot active.
3. **Zero overhead when disabled.** When `--mockrot` is not provided, no runtime hooks are installed
   and no expensive modules are imported. All installed patches must be restored idempotently at the
   end of the test session.
4. **False negative > False positive.** When in doubt (unresolvable type, unavailable signature,
   dynamic target), silently fallback to degraded mode. User trust is the primary asset.
5. **Zero configuration required.** The plugin must work out-of-the-box without requiring a
   `[tool.mockrot]` section. Configuration exists solely for fine-tuning.
6. **Strict performance budget.** Contracts and `TypeAdapter` instances must be compiled
   **only once per target**. Pure validation overhead must stay below **15 ms** across 500 tests
   (hard ceiling: 50 ms total test suite overhead). Every regression must be profiled.
7. **Every violation must be actionable.** Reports must include the exact mock site (file and line),
   target symbol, real contract, and a clear diff of the offending argument or return value.

---

## 5. Known Technical Gotchas

- **`_patch.start()` is insufficient.** `@patch` as a decorator and `with patch(...)` both invoke
  `_patch.__enter__` (which in turn calls `start()`). Intercepting `__enter__` is mandatory to cover
  decorators, context managers, and `pytest-mock` (`mocker.patch`).
- **Pydantic lax mode yields false negatives.** `validate_python("5000", strict=False)` coerces
  `"5000"` into `5000` for an `int`. Mocked values must be validated with **`strict=True`**, with
  explicit handling for necessary structural conversions (e.g. `dict` passed to a Pydantic model).
- **Zombie fields detection.** `TypeAdapter(BaseModel)` ignores extraneous dictionary keys by
  default. Never mutate the user's model configuration: compute obsolete keys independently
  (`model_fields`, aliases, `TypedDict.__annotations__` / `__required_keys__`).
- **Caching strategy.** Standard `lru_cache` fails on unhashable callables, and caching by `id()` is
  bug-prone due to garbage collection ID reuse. Use a robust identity cache (`WeakKeyDictionary`
  with fallback) and preserve `lru_cache` for hashable targets.
- **Handling `self` and `cls`.** Use `inspect.getattr_static` to differentiate functions,
  `staticmethod`, `classmethod`, and bound instance methods, stripping the leading receiver before
  calling `bind()`.
- **Iterable `side_effect`.** Never exhaust generators or iterators in advance: validate each yielded
  value at the moment it is retrieved. Exceptions (both exception classes and instances) are always
  legitimate return paths.
- **`AsyncMock` validation.** Always validate the **resolved return value after `await`**, never the
  coroutine object itself.
- **Pre-specified mocks.** When `autospec=True` or `spec=` is already set on a mock, do not duplicate
  signature errors already raised natively by `unittest.mock`.
- **Non-callable targets.** When patching a class, module, constant, or property: explicitly extract
  the instantiation contract (e.g., class constructor `__init__`) or safely ignore unsupported targets.
- **`monkeypatch.setattr` with real callables.** Patching an attribute with a lambda or custom
  function must undergo the exact same signature and return validation via a transparent wrapper.
- **`ForwardRef` and `TYPE_CHECKING`.** Resolve forward references via the target module's
  `globalns`, falling back to cached AST inspection if necessary. On resolution failure, degrade
  gracefully without raising an exception.
- **`inspect.stack()` vs `sys._getframe()`.** `inspect.stack()` performs blocking `os.stat` calls
  on source files across the entire call stack, breaking async test suites that forbid blocking I/O
  (e.g., Starlette's `blockbuster.BlockingError`) and causing massive CPU overhead. Always use
  `sys._getframe()` for fast, in-memory frame inspection without disk I/O.
- **Pytest internal runner monkeypatching.** Internal plugins such as `pytest-asyncio` monkeypatch
  `item.obj` to synchronize coroutine tests. The `_patched_monkeypatch_setattr` hook must ignore
  internal runner packages (`pytest_asyncio`, `_pytest`, `pluggy`) to avoid treating test runner
  internals as user mocks.
- **Interceptor recursion across module reloads.** When modules are dynamically reloaded or tests
  manipulate patch mechanisms in self-hosting test suites, `_patch.__enter__` may point to a
  previous wrapper instance. Attaching `__mockrot_wrapper__ = True` tags and caching true standard
  library functions (`_ORIGINAL_PATCH_ENTER`, `_ORIGINAL_MONKEYPATCH_SETATTR`) directly on the
  stdlib module namespaces ensures interception calls never enter infinite recursion loops.
- **Unconfigured `NonCallableMock` return values.** `unittest.mock` generates default `MagicMock`
  instances when no `return_value` is specified. Validating these against scalar or model return
  contracts causes immediate false positives. When `isinstance(returned_value, mock.NonCallableMock)`,
  scalar/model return validation is bypassed (respecting Invariant 4: False negative > False positive).
  Concrete drifted values (strings, dicts, integers) continue to be strictly validated.
- **Classmethod and staticmethod descriptors.** When patching class or static methods on a class
  (`patch.object(Cls, "method")`), `temp_original` is a `classmethod` or `staticmethod` descriptor
  for which `callable()` returns `False`. The underlying callable must be unwrapped via
  `type(target) in (classmethod, staticmethod)` and `getattr(target, "__func__", target)`.
- **AsyncMock invocation-time frame resolution.** Resolving caller frames during coroutine execution
  (at `await` time) fails when coroutines are scheduled via `asyncio.create_task` because the test
  function is no longer on the call stack. Frames must be resolved synchronously at the moment
  `mock(*args, **kwargs)` is invoked. Additionally, skipping internal framework frames must be based
  on module prefixes (`frame.f_globals["__name__"]`) rather than file path substrings, avoiding
  false matches when workspaces contain names like `mockrot` or `asyncio`.
- **No emojis.** Never use emojis in code, docstrings, terminal outputs, or documentation. Maintain
  clean, professional ASCII/Unicode typography.

Any newly discovered technical gotcha must be **documented in this section** in the same commit as
its fix.

---

## 6. Senior Engineering Workflow

### Development Cycle for Every Task

1. **Understand:** Read the requirement, inspect existing code and relevant tests, and identify
   edge cases. State the core objective clearly.
2. **Plan:** For changes touching more than one module or the public API, formulate a brief plan
   (impacted files, approach, proposed tests, risks).
3. **Red Test:** Write the failing test first (including positive detection **and** negative tests
   to prevent false positives). For bug fixes, write a reproduction test before fixing the bug.
4. **Implement:** Write minimal, clean code to turn the test green. Avoid speculative features.
5. **Refactor:** Improve naming, structure, and readability without altering external behavior.
6. **Verify:** Run the full verification suite (§10). Never declare a task complete without proof.
7. **Commit:** Produce atomic, clean Conventional Commits (§8).

### Principles

- **Small increments:** One branch = one objective. Keep PRs reviewable in under 15 minutes.
- **Scope discipline:** Do not reformat, rename, or tweak unrelated code. File separate tasks for
  orthogonal improvements.
- **Look before leap:** Reuse existing models and utilities before introducing new abstractions.
- **Dogfooding:** The Mockrot test suite must run with `--mockrot=strict` in CI.

---

## 7. Code Standards

### Language

- **English** for all version-controlled artifacts: code, symbols, docstrings, comments, error
  messages, commits, branches, PRs, and public documentation.
- Conversational interactions with the project maintainer may occur in French when requested.

### Python Guidelines

- `from __future__ import annotations` at the top of every Python file.
- **Complete type safety:** `pyright --strict` with zero errors. `Any` is restricted to external
  mock boundaries and must never leak inward. `# type: ignore` or `# pyright: ignore` requires a
  justification comment on the same line.
- Domain objects: `@dataclass(frozen=True, slots=True)`.
- Short, pure, single-responsibility functions. No import-time side effects.
- **Error handling:** Dedicated exception hierarchy in `errors.py` inheriting from `MockrotError`.
  Never use bare `except:` or catch unhandled generic `Exception` outside the fail-safe boundary in
  `plugin.py`. Always chain exceptions with `from exc`.
- No `print()` calls. User output belongs in `reporter.py`; internal diagnostics belong in standard
  `logging` (`logging.getLogger("mockrot")`) or warnings.
- Google-style docstrings on all public APIs and non-trivial helpers. Comments explain the **why**,
  not the what.
- Ruff rules: `E, W, F, I, B, UP, SIM, RUF, PT, N, C4, TC, ARG, BLE, ERA, PL`.

---

## 8. Git Workflow & Conventions

### Branches

- **`main`**: Protected, always green, production-ready. Linear history only.
- Feature branches: `<type>/<scope-or-fid>-<kebab-case-description>`
  (e.g., `feat/signature-validation`, `fix/async-mock-inspection`).

### Conventional Commits 1.0

```text
<type>(<scope>): <imperative summary in lowercase without trailing period, <= 72 chars>

<optional body: WHY this change was made, technical context, alternatives considered.
Wrap lines at <= 72 characters.>

<optional footer: Closes #12 | Refs: F2>
```

- **Allowed Types:** `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`,
  `style`, `revert`.
- **Allowed Scopes:** `plugin`, `interceptor`, `extractor`, `validator`, `reporter`, `recorder`,
  `fixer`, `models`, `config`, `deps`, `ci`, `cli`.
- Never commit blindly (`git add .` or `git add -A`). Review `git diff --staged` before every commit.
- Never commit secrets, `.env`, caches, virtual environments, or unrelated files.

---

## 9. Testing Strategy

- **Unit tests (`tests/unit/`):** Test `extractor`, `validator`, and `models` in strict isolation
  without initializing pytest plugin hooks.
- **Integration tests (`tests/integration/`):** Test end-to-end plugin behavior using pytest's
  official `pytester` fixture (generating test files, asserting on exit codes and console output).
- **Negative test pairing:** Every positive detection test must be accompanied by an equivalent
  negative test verifying that valid, conforming mocks produce zero warnings and zero violations.
- Full matrix coverage: functions, bound methods, `classmethod`, `staticmethod`, `async def`,
  Pydantic models, dataclasses, `TypedDict`, `Union`/`Optional`, generics, `side_effect` patterns,
  forward references, and C built-ins.
- Strict code coverage ≥ 90% (lines + branches).

---

## 10. Verification Commands

```bash
uv sync                                   # Install all dependencies and tools
uv run ruff format .                      # Format code
uv run ruff check .                       # Lint code
uv run pyright                            # Strict type checking
uv run pytest                             # Run test suite
uv run pytest --cov=mockrot --cov-branch  # Run tests with branch coverage
```

**Full mandatory verification pipeline (must pass before every commit):**

```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest
```

---

## 11. Definition of Done

A task is considered complete **only when**:

- [ ] Requirement is satisfied, including edge cases and negative cases.
- [ ] Automated tests added: positive detection and negative non-detection tests.
- [ ] `ruff format`, `ruff check`, `pyright --strict`, and `pytest` all pass with zero errors.
- [ ] Code coverage remains ≥ 90%.
- [ ] Product invariants are respected (fail-safe boundary, transparency, performance).
- [ ] Documentation, docstrings, or CHANGELOG updated if user-facing behavior changed.
- [ ] Newly discovered technical gotchas documented in §5.
- [ ] Clean, atomic Conventional Commit on a rebased branch.

---

## 12. Architectural Decisions Record (ADR)

- **Standalone CLI:** Lightweight `cli.py` module (console script `mockrot = "mockrot.cli:main"` in
  `pyproject.toml`) delegating to `pytest` with `--mockrot` enabled, supporting `uvx mockrot` out of
  the box.
- **Performance Budget:** Pure validation engine overhead targeted at **< 15 ms** over 500 tests;
  global test suite threshold (including Rich console rendering) set at **< 50 ms**.
- **Accessed-Only Mode:** Scheduled for V1.1 (`--mockrot-mode=accessed-only`) to silence noise on
  legacy codebases without complicating the V1 MVP.
- **LibCST:** Confirmed as an optional extra (`pytest-mockrot[fix]`) to keep the core distribution
  ultra-lightweight.
- **License:** Official **MIT** license.
