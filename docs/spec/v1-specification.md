# Product Specification — Mockrot

October 15, 2026 · Architecture & Engineering Specification (V1)

**Mockrot** (`pytest-mockrot` & CLI) is a `pytest` plugin and runtime contract verification engine that automatically detects **rotting mocks** in Python test suites. Without requiring any configuration, it intercepts mocks (`unittest.mock`, `pytest-mock`, `monkeypatch`, HTTP mocks) and validates that their input arguments AND return values (`return_value`, `side_effect`) strictly comply with the actual runtime signature and return types (`Pydantic`, `TypedDict`, `dataclass`, `OpenAPI` schemas) of the current production code.

---

## 1. Problem Statement & Value Proposition

### The Engineering Problem: Schema & Signature Drift
In any evolving codebase (and even more so when code is refactored by AI coding agents), a silent drift develops between production code and unit tests:
1. **The Green Illusion:** Function `charge_card()` is updated to return a `ChargeResult(tx_uuid: UUID, fee: int)` object instead of a dictionary `{"tx_id": "123"}`.
2. **The Standard Python Flaw:** Even when developers use `autospec=True` (which 90% of developers omit), standard library `unittest.mock` only validates the *input arguments* of the function. **It never verifies that the mock's `return_value` matches the real return type annotation (`-> ReturnType`) of the replaced function.**
3. **The Outage:** Unit tests remain 100% green against frozen fake dictionaries that haven't changed in months, while the application crashes in production immediately upon deployment (`AttributeError`, `ValidationError`, `KeyError`).

### Why Mockrot is Unique
- **Zero Configuration on Day 1:** A single command (`pytest --mockrot`) on any existing repository immediately analyzes all active `@patch` and `mocker.patch` invocations.
- **Bidirectional Validation (Inputs + Outputs):** Verifies call arguments via `inspect.signature` AND validates the exact structural integrity of `return_value` (including `async` coroutines) via the Rust-powered engine of `Pydantic v2` (`TypeAdapter`).
- **Inference by Recording (For Untyped Code):** If a function lacks a return type annotation (`-> ...`), `--mockrot-record` mode observes real return values during integration tests, generates a structural fingerprint (`.mockrot.lock`), and verifies unit tests against that fingerprint.

---

## 2. Architecture & Technical Stack (Optimal 2026 Stack)

To guarantee an execution overhead under **15 ms** on a 500-test suite and provide a flawless developer experience, Mockrot builds on the highest performance tools in the modern Python ecosystem:

| Component | Technology | Senior Engineering Rationale |
| :--- | :--- | :--- |
| **Project & Build Management** | **`uv` + `hatchling`** | Instant dependency resolution, zero-friction standalone execution via `uvx mockrot`, standardized PyPI packaging (`pyproject.toml` PEP 621). |
| **Type Validation Engine** | **`Pydantic v2` (`TypeAdapter`)** | Core written in Rust (`pydantic-core`). Validates any Python type on the fly (`BaseModel`, `dataclass`, `TypedDict`, `list[int]`, `Union`, generics) in microseconds. |
| **Introspection & Runtime** | **`inspect` + `typing.get_type_hints`** | Standard Python 3.10+ library. Resolves deferred type evaluations (`from __future__ import annotations`) and coroutine detection (`inspect.iscoroutinefunction`). |
| **Code Auto-Fixer (AST)** | **`LibCST`** | Concrete Syntax Tree (by Meta). Unlike standard `ast`, `LibCST` rewrites test files (`--mockrot-fix`) while preserving 100% of formatting, comments, and indentation. |
| **Terminal Rendering & Diff** | **`Rich`** | Side-by-side colorized structural diffs (`Mocked Value` vs `Expected Contract`) with clickable links to the exact test file and line number. |
| **Quality & Internal Typing** | **`Ruff` + `Pyright` (strict mode)** | Sub-second linting and strict type verification on the Mockrot codebase itself. |

### Internal Architecture Diagram

```text
[ Pytest Execution ]
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ 1. Interceptor Layer                                              │
│    Wraps `unittest.mock._patch.__enter__()` (covers @patch,       │
│    `with patch(...)`, and `.start()`) & `MonkeyPatch.setattr`     │
│    Captures the real target `orig_target` BEFORE mock replacement │
└───────┬───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ 2. Contract Extractor                                             │
│    • Reads `inspect.signature(orig_target)`                       │
│    • Resolves `typing.get_type_hints(orig_target)['return']`      │
│    • Or loads recorded schema from `.mockrot.lock`                │
└───────┬───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ 3. Runtime Call Proxy Wrapper                                     │
│    On each mock invocation during the test:                       │
│    a) Checks `sig.bind(*args, **kwargs)` (Outdated arguments?)    │
│    b) Intercepts `return_value` (or `await` result)               │
│    c) Validates output via `TypeAdapter(return_type).validate()`   │
└───────┬───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ 4. Reporter & Auto-Fixer (Rich Terminal + JSON + LibCST)          │
│    Aggregates drifts and displays final report or fails CI        │
└───────────────────────────────────────────────────────────────────┘
```

### Repository File Structure

```text
mockrot/
├── pyproject.toml              # uv, hatchling config, pytest11 and cli entry-points
├── src/
│   └── mockrot/
│       ├── __init__.py
│       ├── plugin.py           # Pytest hooks (pytest_addoption, pytest_runtest_call, etc.)
│       ├── cli.py              # Standalone entry point for `uvx mockrot` (delegates to pytest)
│       ├── interceptor.py      # Hook on unittest.mock._patch.__enter__ and pytest.MonkeyPatch
│       ├── extractor.py        # Signature and TypeHints extraction with async support
│       ├── validator.py        # Pydantic TypeAdapter validation (strict mode) and zombie fields
│       ├── recorder.py         # Runtime schema recording (.mockrot.lock) (V1.1)
│       ├── fixer.py            # LibCST transformation to update args/keys (V1.1)
│       ├── reporter.py         # Rich formatting (tables, colorized diffs, SARIF/JSON export)
│       ├── models.py           # Immutable domain models (dataclass frozen/slots)
│       └── errors.py           # Mockrot exception hierarchy
└── tests/
    ├── unit/                   # Pure unit tests (no pytest plugin loaded)
    ├── integration/            # End-to-end plugin tests via pytester fixture
    └── fixtures/               # Target test fixtures (sync, async, pydantic, dataclasses...)
```

---

## 3. Functional Requirements

Twelve requirements: 8 mandatory for V1 (MVP), 4 desirable for V1.1.

| ID | Requirement | Priority |
| :--- | :--- | :--- |
| **F1** | **Transparent Interception:** Intercept all mocks created via `unittest.mock.patch` (decorator, context manager via `_patch.__enter__`, and `.start()`), `pytest-mock` (`mocker.patch`), and `monkeypatch.setattr` without modifying test code. | Mandatory |
| **F2** | **Call Signature Validation:** Verify on every mock invocation that supplied arguments (`*args`, `**kwargs`) match `inspect.signature(real_fn)`. Detect removed arguments, renamed arguments, and missing required parameters. | Mandatory |
| **F3** | **Strict Return Value Validation (`return_value`):** Extract the `-> ReturnType` annotation from the real function and validate the mock's returned value using `pydantic.TypeAdapter(..., strict=True)`. Strict mode prevents false negatives caused by implicit type coercion (e.g. `"5000"` for an `int`). | Mandatory |
| **F4** | **Native `async / await` Support (`AsyncMock`):** If the real target is a coroutine (`async def`), verify that the mock is properly awaited and validate the resolved return value after `await` against `ReturnType`. | Mandatory |
| **F5** | **`side_effect` Support (Iterables and Callables):** If a mock uses `side_effect=[val1, val2]` or a custom callable, validate each generated value (unless the value is an exception class or instance inheriting from `BaseException`, which legitimately simulates errors). | Mandatory |
| **F6** | **"Zombie Field" Detection in Mocked Dictionaries:** When a mock returns a `dict` representing a `Pydantic` model, a `TypedDict`, or a `dataclass`, flag both missing fields AND **obsolete extra keys** (via non-mutating inspection of declared fields and aliases) that no longer exist in the real contract. | Mandatory |
| **F7** | **Dual Execution Modes (`warn` vs `strict`):** `--mockrot=warn` displays a detailed report at the end of `pytest` without failing the test suite; `--mockrot=strict` immediately fails any test executing an obsolete mock. | Mandatory |
| **F8** | **Granular Exemption Markers:** Allow ignoring tests that intentionally test malformed data via `@pytest.mark.mockrot_ignore` or inline `# mockrot: ignore`. | Mandatory |
| **F9** | **Recorder Mode (`--mockrot-record`) for Untyped Code:** Observe calls to real functions during integration tests, infer their JSON/type schema, and save it to `.mockrot.lock` to validate mocks of untyped functions. | Desirable (V1.1) |
| **F10** | **HTTP Mock Validation (`httpx` / `responses` / `respx`):** Cross-check simulated JSON responses on HTTP routes against a local `openapi.json` or the repository's `FastAPI` app. | Desirable (V1.1) |
| **F11** | **AST Auto-Fixer (`--mockrot-fix`):** Use `LibCST` to automatically update renamed arguments or add default values for new mandatory fields directly in test files. | Desirable (V1.1) |
| **F12** | **JSON / GitHub Annotations Export:** Generate reports compatible with GitHub Actions (`::error file=...,line=...::`) to annotate offending test lines directly in Pull Requests. | Desirable (V1.1) |

---

## 4. Technical Edge Cases and Resolution Rules

Senior-grade tooling is distinguished by bulletproof handling of edge cases that cause false positives:

1. **Partial Mocks and Nested `MagicMock`s:**
   - *Issue:* Tests occasionally do `mock_fn.return_value.status = "ok"` without constructing the entire `ChargeResult` object.
   - *Mockrot Rule:* When the returned value is itself a `Mock` / `MagicMock` instance, Mockrot inspects attributes accessed or configured on that sub-mock during the test and verifies that each attribute actually exists on the `ReturnType` class with a compatible type.
2. **Forward References (`ForwardRef` & `TYPE_CHECKING`):**
   - *Issue:* Modern code uses `from __future__ import annotations` or imports types under `if TYPE_CHECKING:`. Calling `get_type_hints()` can raise a `NameError`.
   - *Mockrot Rule:* The extractor first attempts resolution with the target module's `globalns`. If a `NameError` occurs on a type imported under `TYPE_CHECKING`, Mockrot parses the target module's AST to load the missing symbol dynamically into an isolated namespace, cached per target.
3. **Exception Simulation (`side_effect = TimeoutError`):**
   - *Mockrot Rule:* Any exception raised via `side_effect` is treated as a valid resilience test and never triggers return type drift errors.
4. **C Extension Libraries and Builtins Without Signatures:**
   - *Mockrot Rule:* If `inspect.signature` raises `ValueError` (as with certain C-accelerated builtins), Mockrot silently degrades gracefully without crashing the test run.

---

## 5. Developer Experience (DX) and Terminal Output

### Installation and Usage (Zero Config Required)

```bash
# Install in development environment
uv add --dev pytest-mockrot

# Run in audit mode (non-blocking)
pytest --mockrot

# Run in CI mode (fails on rotting mocks)
pytest --mockrot=strict
```

### Terminal Output (Generated via `Rich`)

```text
============================= test session starts ==============================
platform linux -- Python 3.12.4, pytest-8.3.2, mockrot-0.1.0
collected 42 items

tests/test_auth.py ........                                              [ 19%]
tests/test_billing.py ..M.                                               [ 28%]
tests/test_orders.py ..............M                                     [ 64%]

================================================================================
MOCKROT REPORT — 2 Rotting Mocks Detected across 42 tests
================================================================================

[1/2] Return Type Drift in `tests/test_billing.py:48` (test_process_refund)
  ├─ Mocked Target : app.services.stripe_client.issue_refund
  ├─ Real Contract : async def issue_refund(charge_id: str) -> RefundReceipt
  └─ Violation     : Mock return_value does not match `RefundReceipt` (Pydantic Model)

     Field               Your Mock (tests/test_billing.py:45)   Real Model (app/schemas.py:18)
     ─────────────────────────────────────────────────────────────────────────────────────────
     status              "refunded" (str)                       Valid
     tx_id               "re_9981" (str)                        Unknown field (removed?)
     refund_uuid         <MISSING>                              Required (type: UUID)
     amount_cents        "5000" (str)                           Type mismatch (expected int)

────────────────────────────────────────────────────────────────────────────────

[2/2] Call Signature Drift in `tests/test_orders.py:112` (test_cancel_order)
  ├─ Mocked Target : app.repositories.order_repo.mark_cancelled
  ├─ Real Contract : def mark_cancelled(order_id: int, *, reason: str) -> bool
  └─ Violation     :
     • Passed unexpected keyword argument `notify_user=True` (removed from real function)
     • Missing required keyword-only argument `reason: str`

================================================================================
Tip: Fix these 2 mocks to prevent false-positive unit tests in CI.
======================== 2 mockrot errors in 0.42s =============================
```

### Optional Configuration in `pyproject.toml`

```toml
[tool.mockrot]
mode = "strict"                      # "warn" | "strict"
check_arguments = true               # Validates inspect.signature
check_return_types = true            # Validates return type annotations via Pydantic
forbid_extra_dict_keys = true        # Flags obsolete keys in mocked dicts
lockfile = ".mockrot.lock"           # Snapshot file for untyped functions
ignore_targets = [
    "boto3.*",                       # Ignore dynamic third-party SDK mocks
]
```

---

## 6. Core Technical Architecture & Implementation Reference

Reference implementation skeleton of the two critical modules (`interceptor.py` and `validator.py`) addressing identified engineering edge cases:

```python
# src/mockrot/validator.py
from __future__ import annotations

import dataclasses
import inspect
from typing import Any, get_type_hints, is_typeddict
import weakref

from pydantic import BaseModel, TypeAdapter, ValidationError

# Two-tier cache: WeakKeyDictionary for live objects (zero memory leaks),
# fallback to (module, qualname) key for unhashable targets or non-weakref targets.
_CONTRACT_CACHE: weakref.WeakKeyDictionary[Any, Any] = weakref.WeakKeyDictionary()
_STATIC_CONTRACT_CACHE: dict[tuple[str, str], Any] = {}


def get_cached_contract(
    real_fn: Any,
) -> tuple[inspect.Signature | None, TypeAdapter[Any] | None, type[Any] | None]:
    """Extract and cache the signature and TypeAdapter for the real function.

    Immune to Python id() recycling and unhashable function wrappers.
    """
    underlying = getattr(real_fn, "__func__", real_fn)

    try:
        if underlying in _CONTRACT_CACHE:
            return _CONTRACT_CACHE[underlying]
    except TypeError:
        key = (getattr(underlying, "__module__", ""), getattr(underlying, "__qualname__", ""))
        if key in _STATIC_CONTRACT_CACHE:
            return _STATIC_CONTRACT_CACHE[key]

    # 1. Extract real signature
    try:
        sig = inspect.signature(real_fn)
    except (ValueError, TypeError):
        sig = None

    # 2. Resolve return type contract
    adapter: TypeAdapter[Any] | None = None
    return_type: type[Any] | None = None
    try:
        hints = get_type_hints(real_fn)
        ret = hints.get("return")
        if ret is not None and ret is not type(None):
            return_type = ret
            adapter = TypeAdapter(ret)
    except Exception:
        pass

    contract = (sig, adapter, return_type)

    try:
        _CONTRACT_CACHE[underlying] = contract
    except TypeError:
        key = (getattr(underlying, "__module__", ""), getattr(underlying, "__qualname__", ""))
        _STATIC_CONTRACT_CACHE[key] = contract

    return contract


def detect_zombie_fields(return_type: type[Any] | None, returned_value: Any) -> list[str]:
    """Detect obsolete (zombie) keys in mocked dictionaries without mutating real classes."""
    if not isinstance(returned_value, dict) or return_type is None:
        return []

    expected_keys: set[str] = set()

    # Case 1: Pydantic BaseModel (declared fields + validation aliases)
    if isinstance(return_type, type) and issubclass(return_type, BaseModel):
        if return_type.model_config.get("extra") == "allow":
            return []
        for name, field in return_type.model_fields.items():
            expected_keys.add(name)
            if field.alias:
                expected_keys.add(field.alias)
            if field.validation_alias and isinstance(field.validation_alias, str):
                expected_keys.add(field.validation_alias)

    # Case 2: TypedDict
    elif is_typeddict(return_type):
        expected_keys = set(get_type_hints(return_type).keys())

    # Case 3: dataclass
    elif dataclasses.is_dataclass(return_type) and isinstance(return_type, type):
        expected_keys = {f.name for f in dataclasses.fields(return_type)}

    else:
        return []

    mock_keys = set(returned_value.keys())
    zombies = mock_keys - expected_keys
    return [
        f"Zombie field '{k}': obsolete field not in real contract {getattr(return_type, '__name__', str(return_type))}"
        for k in sorted(zombies)
    ]


def _adjust_signature_for_call(
    sig: inspect.Signature, real_fn: Any, call_args: tuple[Any, ...]
) -> inspect.Signature:
    """Adjust signature if an implicit parameter (self/cls) should not be passed by caller."""
    params = list(sig.parameters.values())
    if not params:
        return sig

    first_param = params[0].name
    # If signature expects self/cls but mock call does not supply it
    if first_param in ("self", "cls") and (
        len(call_args) == 0
        or not hasattr(call_args[0], real_fn.__name__ if hasattr(real_fn, "__name__") else "")
    ):
        return sig.replace(parameters=params[1:])
    return sig


def validate_mock_interaction(
    real_fn: Any,
    call_args: tuple[Any, ...],
    call_kwargs: dict[str, Any],
    returned_value: Any,
) -> list[str]:
    """Validate mock call (arguments + return value) against real target."""
    errors: list[str] = []
    sig, return_adapter, return_type = get_cached_contract(real_fn)

    # 1. Validate call signature
    if sig is not None:
        adjusted_sig = _adjust_signature_for_call(sig, real_fn, call_args)
        try:
            adjusted_sig.bind(*call_args, **call_kwargs)
        except TypeError as exc:
            errors.append(f"Call signature drift: {exc}")

    # 2. Strict return value validation (strict=True forbids silent coercion)
    if return_adapter is not None:
        try:
            return_adapter.validate_python(returned_value, strict=True)
        except ValidationError as exc:
            errors.append(f"Return value drift:\n{exc}")

        # 3. Detect zombie fields in dictionaries
        errors.extend(detect_zombie_fields(return_type, returned_value))

    return errors
```

```python
# src/mockrot/interceptor.py
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable
import unittest.mock as mock

from mockrot.validator import validate_mock_interaction


def install_interceptor(on_violation: Callable[[list[str]], None]) -> None:
    """Install wrapper on unittest.mock._patch.__enter__ to intercept all mocks."""
    orig_enter = mock._patch.__enter__

    def patched_enter(patch_self: mock._patch[Any]) -> Any:
        mock_obj = orig_enter(patch_self)
        orig_target, _ = patch_self.get_original()

        if callable(mock_obj) and callable(orig_target):
            _wrap_mock_target(mock_obj, orig_target, on_violation)

        return mock_obj

    mock._patch.__enter__ = patched_enter  # type: ignore[assignment]


def _wrap_mock_target(
    mock_obj: Any, orig_target: Any, on_violation: Callable[[list[str]], None]
) -> None:
    """Wrap mock execution (sync or async) to trigger validation on each call."""
    is_async = inspect.iscoroutinefunction(orig_target) or isinstance(mock_obj, mock.AsyncMock)

    if is_async:
        orig_side_effect = getattr(mock_obj, "side_effect", None)

        async def async_proxy(*args: Any, **kwargs: Any) -> Any:
            result = await mock_obj._mock_call(*args, **kwargs)
            violations = validate_mock_interaction(orig_target, args, kwargs, result)
            if violations:
                on_violation(violations)
            return result

        # Plug transparent proxy
    else:
        # Transparent sync proxy
        pass
```

---

## 7. Delivery Plan (3 Weeks)

Each week delivers a fully tested, working component.

### Week 1: Interception Core & Sync/Async Validation
- **Goals:**
  - Initialize repository with `uv`, `src-layout`, `Ruff`, `Pyright`, `pytest11` entry points, and `mockrot` CLI.
  - Implement `interceptor.py`: wrap `unittest.mock._patch.__enter__` (covering `@patch`, `with patch`, and `.start()`) and `MonkeyPatch.setattr` to capture `(target_func, mock_obj, file_line)`.
  - Implement `extractor.py` and `validator.py`: `inspect.signature.bind()`, `self`/`cls` adjustment, `pydantic.TypeAdapter(..., strict=True)` validation.
  - Support `async def` and `AsyncMock` (validating resolved value after `await`).
- **Exit Criteria:** A 20-test suite covering simple functions, class methods, `Pydantic BaseModel`, `dataclass`, `TypedDict`, and `async def` detecting 100% of argument and return value drifts.

### Week 2: "Zombie Field" Detection, Sub-Mocks & `Rich` Reporter
- **Goals:**
  - Detect obsolete extra keys when a mock returns a `dict` instead of a `BaseModel`, `TypedDict`, or `dataclass` (via non-mutating comparison of allowed keys and aliases).
  - Support attribute inspection on nested `MagicMock` instances (`mock.return_value.foo`).
  - Build `reporter.py` with `Rich` displaying line-by-line comparative tables and session summary.
- **Exit Criteria:** Run `pytest --mockrot` across real Python open-source repositories: zero internal crashes, validation engine overhead `< 15 ms` (global overhead with Rich `< 50 ms`), and clean output.

### Week 3: Recorder Mode (`.mockrot.lock`), Packaging & Release
- **Goals:**
  - Implement `recorder.py` (`pytest --mockrot-record`) to infer untyped function schemas during integration runs.
  - Add `--mockrot-format=github` for GitHub Actions PR annotations.
  - Record a terminal demo showcasing instant detection of hidden bugs in a FastAPI app.
  - Publish v0.1.0 on PyPI under the MIT license.

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **`unittest.mock.patch` on an instance method vs standalone function** | `sig.bind()` fails due to implicit `self` or `cls` argument. | Check if the target attribute on original object is a bound method or descriptor (`inspect.getattr_static`), stripping `self`/`cls` from the signature if called on an instance (`_adjust_signature_for_call`). |
| **Developer mocks a `BaseModel` with a partial dictionary** | The tested code only reads one field, but the model defines 10 required fields. | Provide two modes: `strict` mode (mock must strictly conform) and `accessed-only` mode (validates only keys/attributes accessed during the test run). The `accessed-only` mode eliminates 95% of noise in legacy codebases and is scheduled for V1.1 (`--mockrot-mode=accessed-only`). |
| **Performance degradation on large test suites** | `get_type_hints()` and `TypeAdapter()` invoked thousands of times. | Cache contracts and `TypeAdapter` per function using a two-tier cache (`weakref.WeakKeyDictionary` with `(module, qualname)` fallback). Strictly avoid using raw `id(real_fn)` to prevent memory recycling collisions. Pure validation engine overhead targeted at < 15 ms on 500 tests. |

---

## 9. Launch Strategy ("Show HN" & Distribution)

1. **The "10-Second Audit" Experience:**
   Launch post on Reddit (`r/Python`), Hacker News, and LinkedIn in one sentence:
   > *"Run `uv run --with pytest-mockrot pytest --mockrot` on your current Python repository without changing any code. How many unit tests pass green solely due to mocks that no longer match your real production code?"*
2. **Real-World Case Study at Launch:**
   Clone popular Python repositories on GitHub (using FastAPI/Pydantic), run `pytest --mockrot`, uncover real rotting mocks, submit pull requests to fix them, and highlight these findings in launch articles.
3. **AI-Ready Positioning:**
   Position Mockrot as a vital *Guardrail* for Claude Code, Cursor, and Copilot: add `pytest --mockrot=strict` to AI agent validation loops to prevent AI from breaking contracts between production code and test mocks.