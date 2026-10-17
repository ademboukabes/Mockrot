# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-10-17

### Fixed
- **Behavioral Transparency on `monkeypatch.setattr`:** Prevent breaking descriptor protocol and losing callable object attributes when users monkeypatch attributes. Only wrap user-defined Python functions (`types.FunctionType`), copy metadata using `functools.wraps`, and leave callable class instances (such as `pretend.call_recorder`), bound methods, and built-ins untouched.
- **Pytest Internal Targets Ignored:** Skip target functions and objects belonging to pytest internal machinery (`_pytest`, `pluggy`, `pytest_asyncio`), eliminating false positives when test suites patch internal streams (such as `sys.stdin.buffer.read` under `_pytest.capture`).

### Changed
- **Documentation & Claims:** Updated tagline from "Zero false positives" to "Designed to minimize false positives" and added an explicit "Known Limitations" section in `README.md`.
- **Test Suite Equivalence:** Added integration tests verifying exact behavioral equivalence between test suites run with and without Mockrot.

## [0.1.2] - 2026-10-16

### Fixed
- **Default Mock False Positive:** Eliminate noisy false positives when functions with return annotations are mocked without an explicit `return_value`. Auto-generated `NonCallableMock` instances (such as default `MagicMock` and `AsyncMock`) are exempted from strict scalar/model type validation (respecting Invariant 4: False negative > False positive). Concrete drifted return values remain strictly enforced.
- **Classmethod & Staticmethod Interception:** Properly unwrap `classmethod` and `staticmethod` descriptors during patching (`patch.object(Cls, "method")` and `monkeypatch.setattr`), ensuring all signatures and return types are validated transparently.
- **AsyncMock Frame Resolution:** Resolve violation sites (`MockSite`) synchronously at the moment `mock(*args, **kwargs)` is invoked by caller, ensuring accurate file and line reporting even when coroutines run inside background tasks (`asyncio.create_task`).
- **Robust Module Filtering:** Replace fragile file path substring filtering with module name prefixes (`frame.f_globals["__name__"]`), preventing frame resolution errors in directories matching framework names.

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
