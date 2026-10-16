# Mockrot (`pytest-mockrot`)

[![PyPI version](https://img.shields.io/pypi/v/pytest-mockrot?logo=pypi&logoColor=white&color=3775A9)](https://pypi.org/project/pytest-mockrot/)
[![Python versions](https://img.shields.io/pypi/pyversions/pytest-mockrot?logo=python&logoColor=white&color=3776AB)](https://pypi.org/project/pytest-mockrot/)
[![CI Status](https://github.com/ademboukabes/Mockrot/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ademboukabes/Mockrot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff)
[![Type checker: pyright strict](https://img.shields.io/badge/types-pyright%20strict-2C67B2.svg)](https://github.com/microsoft/pyright)

**Mockrot** is a `pytest` plugin that detects **rotting mocks** : unit test mocks whose call signatures, return types, or dictionary payloads have silently drifted away from real production contracts.

Zero configuration required. Pure transparency. Zero false positives.

---

## The Problem: The Green Test Illusion

In Python testing, `unittest.mock.patch` and `pytest-mock` are ubiquitous. However, standard mocking tools create a dangerous false sense of security:

```python
# 1. Production code evolves: return type changed from dict to Pydantic model
def fetch_invoice(invoice_id: str) -> InvoiceReceipt: ...


# 2. Legacy unit test written months ago:
@patch("app.billing.fetch_invoice", return_value={"id": "inv_123", "amount": "invalid_str"})
def test_checkout(mock_fetch):
    result = checkout_cart("inv_123")
    assert result is True
```

- **The test is 100% green.** Standard `unittest.mock` never verifies that `return_value` conforms to `InvoiceReceipt`.
- Even `autospec=True` only checks call parameter names—it **never** validates return values.
- **Production crashes** with `ValidationError`, `AttributeError`, or `KeyError`.

This issue is amplified when AI coding assistants refactor production signatures: existing unit tests keep passing on obsolete mock data while production breaks.

---

## The Solution: Bidirectional Contract Verification

Mockrot intercepts mocks during test execution, extracts the true production contract (`inspect.signature` + `typing.get_type_hints`), and validates both inputs and outputs at runtime using **Pydantic v2 TypeAdapter**:

```text
pytest execution
       │
       ▼
interceptor.py  ──▶  Captures real target & mock calls
       │
       ▼
extractor.py    ──▶  Resolves signature, type hints & async contracts
       │
       ▼
validator.py    ──▶  Validates parameters, return types & zombie fields
       │
       ▼
reporter.py     ──▶  Displays actionable terminal diffs without emojis
```

---

## Key Features

- **Call Signature Validation:** Catches unexpected keyword arguments, missing required parameters, and positional mismatches.
- **Strict Return Type Validation:** Uses Pydantic v2 `TypeAdapter` in strict mode to ensure scalar types (`int`, `str`, `bool`), Pydantic models, dataclasses, and `TypedDict` are respected.
- **Zombie Field Detection:** Identifies obsolete keys in mocked dictionaries that no longer exist in the target model (`BaseModel`, `dataclass`, or `TypedDict`).
- **Async & Coroutine Mismatch Detection:** Flags asynchronous targets mocked with synchronous values or un-awaited coroutines.
- **Side Effect Verification:** Validates every item produced by `side_effect` iterables and callables while preserving legitimate exception simulation.
- **Fail-Safe Architecture:** Internal errors in Mockrot are caught at an isolated boundary and converted to warnings—**Mockrot will never crash your test suite**.
- **Negligible Overhead:** Compiled schemas and TypeAdapters are cached per target (< 5.5 µs per validation, ~25 ms overhead over 500 tests).
- **Line-Level Exemptions:** Easily bypass legacy or intentional mock mismatches with `# mockrot: ignore`.

---

## Installation

```bash
# With pip
pip install pytest-mockrot

# With uv
uv add --dev pytest-mockrot

# With poetry
poetry add --group dev pytest-mockrot
```

Or run directly without installing using `uvx`:

```bash
uvx mockrot
```

---

## Quickstart

### 1. Audit Mode (Default)

Run your tests with `--mockrot`. Mockrot runs your entire test suite without failing tests, and summarizes any rotting mocks at the end of the session:

```bash
pytest --mockrot
# or explicitly
pytest --mockrot=warn
```

### 2. Strict CI Mode (Gatekeeper)

In your CI/CD pipeline, enforce that no rotting mocks enter your codebase. Any contract violation immediately fails the test session with exit code `1`:

```bash
pytest --mockrot=strict
```

---

## Example Terminal Output

When a mock drifts from its real contract, Mockrot provides a clean, actionable report:

```text
Mockrot detected rotting mock (return_type_drift):
  Target:   app.billing.fetch_invoice
  Site:     tests/unit/test_checkout.py:42 (test_checkout)
  Error:    1 validation error for InvoiceReceipt
            amount_cents
              Field required [type=missing, input_type=dict]
  Expected: InvoiceReceipt
  Actual:   dict: {'id': 'inv_123', 'amount': 'invalid_str'}

               Type Drift Comparison               
╭───────────────────┬─────────────────────────────╮
│ Expected Contract │ Actual Mock Output          │
├───────────────────┼─────────────────────────────┤
│ InvoiceReceipt    │ dict: {'id': 'inv_123', ...} │
╰───────────────────┴─────────────────────────────╯

Zombie Field in Mocked Dictionary:
  Target:   app.users.get_profile
  Site:     tests/unit/test_users.py:88 (test_profile)
  Error:    Zombie field 'legacy_token' detected in mocked dictionary for UserProfile.
            This field is not declared on the production contract.
```

---

## Ignoring Known Mocks

If a test intentionally mocks an invalid signature (e.g. testing error handling or legacy compatibility), you can exempt it:

### Inline Comment (Recommended)

```python
with patch("app.orders.calculate_taxes", return_value="invalid") as mock_calc:
    mock_calc(100, 0.2)  # mockrot: ignore
```

### Pytest Marker

```python
@pytest.mark.mockrot_ignore
def test_legacy_edge_case(): ...
```

---

## Configuration

Mockrot requires zero configuration out of the box. You can optionally customize its behavior in `pyproject.toml`:

```toml
[tool.mockrot]
mode = "strict"          # Options: "warn" (default) or "strict"
exclude_targets = [
    "external_legacy_lib.*",
]
```

---

## Real-World Battle Tested

Mockrot is battle-tested against real production projects:
- **Starlette (ASGI Framework):** 476 tests passed in 1.16s with zero false positives and compatibility with async blocking I/O detectors (`blockbuster`).
- **Production FastAPI & Pydantic Microservices:** Validated across asynchronous database calls, MinIO S3 clients, Google Drive OAuth integrations, and background workers.

---

## Comparison

| Feature | `unittest.mock` | `unittest.mock(autospec=True)` | `pytest-mockrot` |
| :--- | :---: | :---: | :---: |
| Signature verification | Partial | Yes | **Yes** |
| Return type validation | No | No | **Yes (Pydantic v2 strict)** |
| Zombie field detection | No | No | **Yes** |
| Async coroutine validation | No | No | **Yes** |
| Zero configuration | Yes | No (`autospec=True` needed) | **Yes (`pytest --mockrot`)** |
| Terminal diff diagnostic | No | No | **Yes (Rich formatting)** |

---

## Contributing

We welcome contributions! Please see [AGENTS.md](./AGENTS.md) for architecture rules, technical invariants, and coding standards.

```bash
# Clone the repository
git clone https://github.com/ademboukabes/Mockrot.git
cd Mockrot

# Install dependencies with uv
uv sync

# Run format, lint, type checks, and tests
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest --cov=mockrot --cov-branch
```

---

## License

This project is licensed under the terms of the [MIT License](./LICENSE).
