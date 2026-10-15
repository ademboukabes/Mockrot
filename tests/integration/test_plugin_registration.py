"""Integration tests for pytest plugin registration and CLI options."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_displays_mockrot_help_option_when_pytest_help_requested(
    pytester: pytest.Pytester,
) -> None:
    result = pytester.runpytest("--help")
    result.stdout.fnmatch_lines(
        [
            "*Mock contract verification:*",
            "*--mockrot*",
        ]
    )
    assert result.ret == 0


def test_displays_mockrot_header_when_mockrot_flag_enabled(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile("""
        def test_sample():
            assert True
    """)
    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
        ]
    )
    assert result.ret == 0


def test_omits_mockrot_header_when_mockrot_flag_disabled(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile("""
        def test_sample():
            assert True
    """)
    result = pytester.runpytest()
    assert "mockrot: active" not in result.stdout.str()
    assert result.ret == 0
