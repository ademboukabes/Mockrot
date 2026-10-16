# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-10-16

### Fixed
- **Interceptor Recursion Guard:** Immunize `unittest.mock._patch.__enter__` and `MonkeyPatch.setattr` against recursion loops during dynamic module reloads or self-hosting test suites by preserving immutable references to native Python standard library methods.
- **Test Suite Hygiene:** Clean up top-level module reload calls in unit tests to ensure test sessions remain stable and non-mutating.

### Changed
- **Documentation & Open Source Polish:** Fully standardized open-source governance documents (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`), translated project specifications and agent directives into English, and updated official badges.

## [0.1.0] - 2026-10-16

### Added
- **Core Interception (F1):** Transparent proxy for `unittest.mock._patch` (`@patch`, `with patch(...)`, `.start()`) and `pytest.MonkeyPatch.setattr` with fast, non-blocking stack inspection via `sys._getframe`.
- **Signature Validation (F2):** Runtime signature contract extraction via `inspect.signature` with `self`/`cls` parameter binding and keyword argument validation.
- **Return Type Validation (F3):** Strict runtime type validation of scalar types, Pydantic v2 models, dataclasses, and TypedDicts powered by `pydantic.TypeAdapter`.
- **Async & Coroutine Support (F4):** Interception and validation of `async def` targets, coroutines, and `AsyncMock` post-await values.
- **Side Effect Handling (F5):** Dynamic per-item validation for `side_effect` generators, iterables, and callables, with built-in immunity for intentional exception simulation.
- **Zombie Field Detection (F6):** Automatic detection of deleted or renamed keys in mocked dictionaries for `BaseModel`, `dataclass`, and `TypedDict`.
- **Execution Modes (F7):** Non-blocking audit mode (`--mockrot=warn`) and strict CI gatekeeper mode (`--mockrot=strict`).
- **Exemptions & Filtering (F8):** Line-level `# mockrot: ignore` comments and `@pytest.mark.mockrot_ignore` test marks.
- **Rich Terminal Reporting:** Clean, emoji-free terminal output with actionable diff tables and line-number diagnostics.
- **CLI Entry Point:** Standalone `mockrot` command allowing instant execution via `uvx mockrot`.
- **CI & Quality Assurance:** Complete GitHub Actions test matrix across Python 3.10, 3.11, 3.12, and 3.13 with 92% code coverage and strict Pyright verification.
