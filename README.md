# Mockrot (`pytest-mockrot`)

[![CI](https://github.com/adem-bks/Mockrot/actions/workflows/ci.yml/badge.svg)](https://github.com/adem-bks/Mockrot/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Mockrot** is a `pytest` plugin that detects **rotting mocks** : unit test mocks whose call arguments or return values have drifted from the real production contract (`inspect.signature` and `Pydantic` / `TypedDict` / `dataclass` return annotations).

---

## The Problem: The Green Test Illusion

`unittest.mock` (even with `autospec=True`) validates input arguments but **never validates return values** against target annotations:

```python
# Production code evolved from dict to Pydantic model:
def get_receipt(charge_id: str) -> RefundReceipt: ...

# Unit test written months ago:
@patch("app.billing.get_receipt", return_value={"tx_id": "legacy_123"})
def test_billing(mock_get):
    # Test passes 100% green!
    # Production crashes with AttributeError or ValidationError!
```

## Solution: Bidirectional Contract Verification

Mockrot intercepts mocks during pytest runs, resolves the real signature and return type, and strictly validates both inputs and outputs:

```bash
# Run in non-blocking audit mode
pytest --mockrot

# Run in CI to block rotting mocks
pytest --mockrot=strict

# Run without installing via uvx
uvx mockrot
```

## Key Invariants

1. **Never crash user test suites**: Fail-safe boundary handles introspection quirks gracefully.
2. **Total transparency**: Mocks return exact mock values; tests behave identically with or without Mockrot in warn mode.
3. **Zero configuration**: Runs out of the box without any config files.
4. **Performance budget**: Contracts and `TypeAdapter` instances are compiled once per target (< 15 ms pure engine overhead).

## Contributing

See [AGENTS.md](./AGENTS.md) for coding standards, architecture, and git workflow.

## License

MIT License. See [LICENSE](./LICENSE).
