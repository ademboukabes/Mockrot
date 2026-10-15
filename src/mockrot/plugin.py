"""Pytest plugin hooks and CLI option registration for Mockrot."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI options and ini configurations for Mockrot."""
    group = parser.getgroup("mockrot", "Mock contract verification")
    group.addoption(
        "--mockrot",
        action="store",
        dest="mockrot_mode",
        nargs="?",
        const="warn",
        default=None,
        choices=["warn", "strict"],
        help="Enable Mockrot contract verification ('warn' or 'strict').",
    )
    parser.addini(
        "mockrot_mode",
        help="Default Mockrot execution mode ('warn' or 'strict').",
        default=None,
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure Mockrot markers and session setup."""
    config.addinivalue_line(
        "markers",
        "mockrot_ignore: ignore Mockrot contract validation for marked test item.",
    )


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Provide Mockrot status line in pytest header when active."""
    mode: str | None = config.getoption("mockrot_mode")
    if mode:
        return [f"mockrot: active (mode={mode})"]
    return []
