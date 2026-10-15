"""End-to-end integration tests for transparent interception using pytester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_interceptor_runs_transparently_under_pytest_mockrot(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile("""
        import math
        from unittest.mock import patch

        @patch("math.sqrt", return_value=999)
        def test_patch_transparent(mock_sqrt):
            val = math.sqrt(4)
            assert val == 999
            mock_sqrt.assert_called_once_with(4)

        def test_context_manager_transparent():
            with patch("math.floor", return_value=42) as mock_floor:
                val = math.floor(3.14)
                assert val == 42
                assert mock_floor.call_count == 1
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*2 passed*",
        ]
    )
    assert result.ret == 0


def test_interceptor_does_not_affect_tests_when_disabled(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile("""
        import math
        from unittest.mock import patch

        @patch("math.sqrt", return_value=123)
        def test_without_mockrot(mock_sqrt):
            assert math.sqrt(16) == 123
    """)

    result = pytester.runpytest()
    assert "mockrot: active" not in result.stdout.str()
    result.stdout.fnmatch_lines(
        [
            "*1 passed*",
        ]
    )
    assert result.ret == 0
