"""Unit tests for standalone mockrot CLI."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mockrot.cli import main


def test_invokes_pytest_with_warn_mode_when_no_mockrot_argument_provided() -> None:
    with patch("pytest.main", return_value=pytest.ExitCode.OK) as mock_pytest:
        exit_code = main(["-k", "test_demo"])

        assert exit_code == 0
        mock_pytest.assert_called_once_with(["--mockrot=warn", "-k", "test_demo"])


def test_preserves_explicit_mockrot_mode_when_passed_in_arguments() -> None:
    with patch("pytest.main", return_value=pytest.ExitCode.OK) as mock_pytest:
        exit_code = main(["--mockrot=strict", "-q"])

        assert exit_code == 0
        mock_pytest.assert_called_once_with(["--mockrot=strict", "-q"])
