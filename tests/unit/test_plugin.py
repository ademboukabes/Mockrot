"""Unit tests for plugin hooks and configuration."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import mockrot.plugin
from mockrot.plugin import pytest_addoption, pytest_configure, pytest_report_header

importlib.reload(mockrot.plugin)


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
