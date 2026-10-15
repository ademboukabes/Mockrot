# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project bootstrap with `uv`, `hatchling`, PEP 621 `pyproject.toml`, and `src` layout.
- Initial domain models in `mockrot.models` (`Contract`, `MockSite`, `Violation`).
- Base error hierarchy in `mockrot.errors` (`MockrotError`).
- Pytest plugin entry point registering `--mockrot` option and `@pytest.mark.mockrot_ignore`.
- Standalone CLI entry point `mockrot` delegating to pytest.
- Strict `pyright` and `ruff` configurations.
- Matrix CI workflow across Python 3.10 to 3.13.
