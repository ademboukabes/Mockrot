"""Pytest plugin hooks and CLI option registration for Mockrot."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from mockrot.interceptor import install_interceptor, uninstall_interceptor
from mockrot.models import Violation
from mockrot.validator import validate_interaction

if TYPE_CHECKING:
    from mockrot.models import MockInteraction


@dataclass
class MockrotSession:
    """Session state holding detected contract violations and active test item."""

    mode: str
    violations: list[Violation] = field(default_factory=list[Violation])
    current_item: pytest.Item | None = None


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
    raw_mode: str | None = config.getoption("mockrot_mode") or config.getini("mockrot_mode")
    if not raw_mode:
        return

    mode = str(raw_mode)
    session = MockrotSession(mode=mode)
    config._mockrot_session = session  # type: ignore[attr-defined]

    def on_interaction(interaction: MockInteraction) -> None:
        try:
            # Check if active test item has exemption marker
            item = session.current_item
            if item is not None and item.get_closest_marker("mockrot_ignore") is not None:
                return

            violations = validate_interaction(interaction)
            if not violations:
                return

            session.violations.extend(violations)

            if session.mode == "strict":
                first = violations[0]
                fail_msg = (
                    f"\nMockrot detected rotting mock ({first.kind.value}):\n"
                    f"  Target:   {first.target_name}\n"
                    f"  Site:     {first.site.file_path}:{first.site.line_number}\n"
                    f"  Error:    {first.message}\n"
                    f"  Expected: {first.expected}\n"
                    f"  Actual:   {first.actual}"
                )
                pytest.fail(fail_msg, pytrace=False)
        except Exception as exc:  # noqa: BLE001 - Invariant 1: fail-safe boundary to never crash user tests
            warnings.warn(
                f"Mockrot internal warning during mock validation: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )

    install_interceptor(on_interaction)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Clean up session and restore original patch methods at session teardown."""
    if hasattr(config, "_mockrot_session"):
        delattr(config, "_mockrot_session")
    uninstall_interceptor()


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Track currently executing test item for exemption checks."""
    session: MockrotSession | None = getattr(item.config, "_mockrot_session", None)
    if session is not None:
        session.current_item = item


def pytest_runtest_teardown(item: pytest.Item) -> None:
    """Clear active test item upon test completion."""
    session: MockrotSession | None = getattr(item.config, "_mockrot_session", None)
    if session is not None and session.current_item is item:
        session.current_item = None


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, exitstatus: int, config: pytest.Config
) -> None:
    """Display summary of rotting mocks in warn mode."""
    del exitstatus
    session: MockrotSession | None = getattr(config, "_mockrot_session", None)
    if session is None or not session.violations:
        return

    terminalreporter.section("Mockrot: Rotting Mocks Detected", sep="=", yellow=True)
    for v in session.violations:
        terminalreporter.write_line(
            f"  [{v.kind.value}] {v.target_name} at {v.site.file_path}:{v.site.line_number}"
        )
        terminalreporter.write_line(f"    Expected: {v.expected}")
        terminalreporter.write_line(f"    Actual:   {v.actual}")
        terminalreporter.write_line(f"    Error:    {v.message}")

    count = len(session.violations)
    terminalreporter.write_line(
        f"\n{count} rotting mock(s) detected. Fix these mocks to prevent false positives in CI."
    )


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Provide Mockrot status line in pytest header when active."""
    mode: str | None = config.getoption("mockrot_mode", default=None)
    if mode:
        return [f"mockrot: active (mode={mode})"]
    return []
