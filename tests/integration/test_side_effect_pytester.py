"""Integration tests verifying end-to-end side_effect validation (F5) with pytester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_side_effect_iterable_warn_mode_reports_summary_on_drift(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        inventory="""
        def check_stock(item_id: int) -> int:
            return 42
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import inventory

        @patch("inventory.check_stock")
        def test_stock_sequence(mock_stock):
            mock_stock.side_effect = [10, "out_of_stock", 30]

            # 1st call: valid int 10
            assert inventory.check_stock(1) == 10
            # 2nd call: invalid str 'out_of_stock' (drift)
            assert inventory.check_stock(2) == "out_of_stock"
            # 3rd call: valid int 30
            assert inventory.check_stock(3) == 30
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*= Mockrot: Rotting Mocks Detected =*",
            "*[return_type_drift]*inventory.check_stock*",
            "*Expected: int*",
            "*Actual:*str: 'out_of_stock'*",
            "*1 rotting mock(s) detected*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_side_effect_iterable_strict_mode_fails_at_drift(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        inventory="""
        def check_stock(item_id: int) -> int:
            return 42
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import inventory

        @patch("inventory.check_stock")
        def test_stock_sequence_strict(mock_stock):
            mock_stock.side_effect = [10, "out_of_stock", 30]

            inventory.check_stock(1)
            # Fails on this second call
            inventory.check_stock(2)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (return_type_drift):*",
            "*Target:*inventory.check_stock*",
            "*Expected: int*",
            "*Actual:*str: 'out_of_stock'*",
            "*1 failed*",
        ]
    )
    assert result.ret != 0


def test_side_effect_iterable_with_exception_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        service="""
        def fetch_record(record_id: int) -> int:
            return record_id * 10
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import pytest
        import service

        @patch("service.fetch_record")
        def test_retry_on_timeout(mock_fetch):
            mock_fetch.side_effect = [
                100,
                TimeoutError("transient network failure"),
                300,
            ]

            # 1. First call succeeds
            assert service.fetch_record(1) == 100

            # 2. Second call raises TimeoutError (resilience test)
            with pytest.raises(TimeoutError, match="transient network failure"):
                service.fetch_record(2)

            # 3. Third call succeeds
            assert service.fetch_record(3) == 300
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(["*1 passed*"])
    assert result.ret == 0


def test_side_effect_custom_callable_strict_mode_detects_drift(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        calc="""
        def double(x: int) -> int:
            return x * 2
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import calc

        @patch("calc.double")
        def test_callable_drift(mock_calc):
            # Custom callable returns string instead of int
            mock_calc.side_effect = lambda x: f"number_{x}"
            calc.double(5)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (return_type_drift):*",
            "*Target:*calc.double*",
            "*Expected: int*",
            "*Actual:*str: 'number_5'*",
            "*1 failed*",
        ]
    )
    assert result.ret != 0


def test_side_effect_callable_returning_exception_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api="""
        def get_status(code: int) -> int:
            return code
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import api

        @patch("api.get_status")
        def test_callable_returning_exception_instance(mock_api):
            # Callable returning an Exception instance to simulate error state
            mock_api.side_effect = lambda code: NotImplementedError("status unavailable")
            res = api.get_status(503)
            assert isinstance(res, NotImplementedError)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(["*1 passed*"])
    assert result.ret == 0


def test_side_effect_lazy_generator_is_not_consumed_in_advance(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        counter="""
        def next_id() -> int:
            return 1
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import counter

        def infinite_numbers():
            n = 100
            while True:
                yield n
                n += 1

        @patch("counter.next_id")
        def test_infinite_generator(mock_counter):
            mock_counter.side_effect = infinite_numbers()
            # Only consume 2 elements from the infinite generator
            assert counter.next_id() == 100
            assert counter.next_id() == 101
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(["*1 passed*"])
    assert result.ret == 0
