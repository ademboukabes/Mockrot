"""Unit tests for plugin hooks and configuration."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import mockrot.plugin
from mockrot.models import MockSite, Violation, ViolationKind
from mockrot.plugin import (
    pytest_addoption,
    pytest_configure,
    pytest_report_header,
    pytest_unconfigure,
)


def test_registers_mockrot_cli_group_when_addoption_called() -> None:
    parser = MagicMock()
    group = MagicMock()
    parser.getgroup.return_value = group

    pytest_addoption(parser)

    parser.getgroup.assert_called_once_with("mockrot", "Mock contract verification")
    group.addoption.assert_called_once()
    parser.addini.assert_called_once()


def test_registers_marker_when_configure_called() -> None:
    config = MagicMock()
    config.getoption.return_value = None

    pytest_configure(config)

    config.addinivalue_line.assert_called_once_with(
        "markers",
        "mockrot_ignore: ignore Mockrot contract validation for marked test item.",
    )


def test_reports_header_when_mode_is_active() -> None:
    config = MagicMock()
    config.getoption.return_value = "strict"

    header = pytest_report_header(config)

    assert header == ["mockrot: active (mode=strict)"]


def test_omits_header_when_mode_is_inactive() -> None:
    config = MagicMock()
    config.getoption.return_value = None

    header = pytest_report_header(config)

    assert header == []


def test_installs_interceptor_when_mockrot_mode_active() -> None:
    config = MagicMock()
    config.getoption.return_value = "warn"

    mock_install: MagicMock = MagicMock()
    orig = mockrot.plugin.install_interceptor
    mockrot.plugin.install_interceptor = mock_install
    try:
        pytest_configure(config)
        assert mock_install.call_count == 1
    finally:
        mockrot.plugin.install_interceptor = orig


def test_uninstalls_interceptor_when_session_unconfigures() -> None:
    config = MagicMock()

    mock_uninstall: MagicMock = MagicMock()
    orig = mockrot.plugin.uninstall_interceptor
    mockrot.plugin.uninstall_interceptor = mock_uninstall
    try:
        pytest_unconfigure(config)
        assert mock_uninstall.call_count == 1
    finally:
        mockrot.plugin.uninstall_interceptor = orig


def test_failsafe_boundary_emits_warning_on_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = MagicMock()
    config.getoption.return_value = "warn"

    captured_cb: list[Any] = []

    def fake_install(cb: Any) -> None:
        captured_cb.append(cb)

    monkeypatch.setattr(mockrot.plugin, "install_interceptor", fake_install)

    def failing_validate(interaction: Any) -> list[Any]:
        del interaction
        raise RuntimeError("boom in validator")

    monkeypatch.setattr(mockrot.plugin, "validate_interaction", failing_validate)

    pytest_configure(config)
    assert len(captured_cb) == 1

    interaction = MagicMock()
    with pytest.warns(
        RuntimeWarning, match="Mockrot internal warning during mock validation: boom in validator"
    ):
        captured_cb[0](interaction)


def test_terminal_summary_reports_violations() -> None:
    config = MagicMock()
    session = mockrot.plugin.MockrotSession(mode="warn")
    session.violations.append(
        Violation(
            site=MockSite(file_path="test_a.py", line_number=10),
            target_name="pkg.fn",
            kind=ViolationKind.SIGNATURE_MISMATCH,
            message="bad arg",
            expected="(x: int)",
            actual="args=()",
        )
    )
    config._mockrot_session = session

    terminalreporter = MagicMock()
    mockrot.plugin.pytest_terminal_summary(terminalreporter, 0, config)

    terminalreporter.section.assert_called_once_with(
        "Mockrot: Rotting Mocks Detected", sep="=", yellow=True
    )
    assert terminalreporter.write_line.call_count >= 5


def test_runtest_setup_and_teardown_tracks_current_item() -> None:
    item = MagicMock()
    session = mockrot.plugin.MockrotSession(mode="strict")
    item.config._mockrot_session = session

    mockrot.plugin.pytest_runtest_setup(item)
    assert session.current_item is item

    mockrot.plugin.pytest_runtest_teardown(item)
    assert session.current_item is None
