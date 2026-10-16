"""Integration tests for Rich reporter and inline '# mockrot: ignore' exemptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_line_level_ignore_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def compute_tax(amount: int, rate: float = 0.2) -> float:
            return amount * rate
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import app

        @patch("app.compute_tax")
        def test_ignore_on_call_line(mock_tax):
            # Deliberately invalid call, ignored via inline comment
            app.compute_tax(wrong_arg=100)  # mockrot: ignore
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_decorator_level_ignore_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def compute_tax(amount: int, rate: float = 0.2) -> float:
            return amount * rate
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import app

        @patch("app.compute_tax")  # mockrot: ignore
        def test_ignore_on_decorator(mock_tax):
            app.compute_tax(wrong_arg=100)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_context_manager_ignore_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def compute_tax(amount: int, rate: float = 0.2) -> float:
            return amount * rate
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import app

        def test_ignore_on_with_statement():
            with patch("app.compute_tax"):  # mockrot: ignore
                app.compute_tax(wrong_arg=100)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_rich_terminal_report_elements_in_warn_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def get_value() -> int:
            return 42
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import app

        @patch("app.get_value", return_value="not_an_int")
        def test_bad_return(mock_val):
            app.get_value()
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*= Mockrot: Rotting Mocks Detected =*",
            "*MOCKROT REPORT - 1 Rotting Mock(s) Detected across 1 test(s)*",
            "*[return_type_drift]*app.get_value*",
            "*Expected:*int*",
            "*Actual:*str:*",
            "*Tip: Fix these 1 mock(s)*",
            "*1 rotting mock(s) detected*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0
