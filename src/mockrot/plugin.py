"""Pytest plugin hooks and CLI option registration for Mockrot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mockrot.interceptor import install_interceptor, uninstall_interceptor

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
    """Configure Mockrot markers, session setup, and install interceptor if enabled."""
    config.addinivalue_line(
        "markers",
        "mockrot_ignore: ignore Mockrot contract validation for marked test item.",
    )
    mode: str | None = config.getoption("mockrot_mode")
    if mode:
        # Active interception listener (wired to validation in upcoming stages)
        install_interceptor(lambda _: None)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Clean up and restore original patch methods at session teardown."""
    del config
    uninstall_interceptor()


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Provide Mockrot status line in pytest header when active."""
    mode: str | None = config.getoption("mockrot_mode")
    if mode:
        return [f"mockrot: active (mode={mode})"]
    return []
