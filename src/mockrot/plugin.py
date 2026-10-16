"""Pytest plugin hooks and CLI option registration for Mockrot."""

from __future__ import annotations

import inspect
import linecache
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from mockrot.interceptor import install_interceptor, uninstall_interceptor
from mockrot.models import MockSite, Violation
from mockrot.reporter import (
    format_terminal_summary,
    format_violation_for_strict,
)
from mockrot.validator import validate_interaction

if TYPE_CHECKING:
    from mockrot.models import MockInteraction


def _is_site_ignored(site: MockSite | Any) -> bool:
    """Return True if the source line where the mock was called or defined is ignored."""
    file_path = getattr(site, "file_path", None)
    line_number = getattr(site, "line_number", None)
    if not isinstance(file_path, str) or not isinstance(line_number, int) or line_number <= 0:
        return False
    try:
        line = linecache.getline(file_path, line_number)
        if "mockrot: ignore" in line or "mockrot:ignore" in line:
            return True
        if line_number > 1:
            prev = linecache.getline(file_path, line_number - 1)
            if "mockrot: ignore" in prev or "mockrot:ignore" in prev:
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _is_item_ignored(item: pytest.Item | Any) -> bool:
    """Return True if active test item has exemption marker or decorator with # mockrot: ignore."""
    if item is None:
        return False
    marker_getter = getattr(item, "get_closest_marker", None)
    if callable(marker_getter) and marker_getter("mockrot_ignore") is not None:
        return True
    try:
        obj = getattr(item, "obj", None)
        if obj is not None and callable(obj):
            lines, _ = inspect.getsourcelines(obj)
            for line in lines:
                stripped = line.strip()
                if "mockrot: ignore" in stripped or "mockrot:ignore" in stripped:
                    return True
                if stripped.startswith("def ") or stripped.startswith("async def "):
                    break
    except Exception:  # noqa: BLE001
        return False
    return False


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
            # Check if active test item or call site has exemption
            item = session.current_item
            if _is_item_ignored(item) or _is_site_ignored(interaction.site):
                return

            violations = validate_interaction(interaction)
            if not violations:
                return

            session.violations.extend(violations)

            if session.mode == "strict":
                first = violations[0]
                pytest.fail(format_violation_for_strict(first), pytrace=False)
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
    """Display summary of rotting mocks in warn mode via Rich reporter."""
    del exitstatus
    session: MockrotSession | None = getattr(config, "_mockrot_session", None)
    if session is None or not session.violations:
        return

    terminalreporter.section("Mockrot: Rotting Mocks Detected", sep="=", yellow=True)

    hasmarkup = getattr(terminalreporter, "hasmarkup", False)
    raw_collected = getattr(terminalreporter, "_numcollected", None)
    total_collected = raw_collected if isinstance(raw_collected, int) else len(session.violations)

    summary_text = format_terminal_summary(
        violations=session.violations,
        total_tests=total_collected,
        force_terminal=bool(hasmarkup),
    )

    for line in summary_text.splitlines():
        terminalreporter.write_line(line)


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Provide Mockrot status line in pytest header when active."""
    mode: str | None = config.getoption("mockrot_mode", default=None)
    if mode:
        return [f"mockrot: active (mode={mode})"]
    return []
