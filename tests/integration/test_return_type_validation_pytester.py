"""Integration tests verifying end-to-end return type validation (F3) with pytester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_return_type_drift_warn_mode_reports_summary(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        billing="""
        def calculate_fee(amount: int) -> int:
            return amount // 10
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import billing

        @patch("billing.calculate_fee", return_value="5000")
        def test_fee_type_drift(mock_fee):
            # Target specifies -> int, mock returns string "5000"
            fee = billing.calculate_fee(100)
            assert fee == "5000"
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*= Mockrot: Rotting Mocks Detected =*",
            "*[return_type_drift]*billing.calculate_fee*",
            "*Expected: int*",
            "*Actual:*str: '5000'*",
            "*1 rotting mock(s) detected*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_return_type_drift_strict_mode_fails_test(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        billing="""
        def calculate_fee(amount: int) -> int:
            return amount // 10
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import billing

        @patch("billing.calculate_fee", return_value="5000")
        def test_fee_type_drift_strict(mock_fee):
            billing.calculate_fee(100)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (return_type_drift):*",
            "*Target:*billing.calculate_fee*",
            "*Input should be a valid integer*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1


def test_return_type_pydantic_model_strict_rejection(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        services="""
        from pydantic import BaseModel

        class User(BaseModel):
            id: int
            username: str

        def get_user(user_id: int) -> User:
            return User(id=user_id, username="admin")
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import services

        @patch("services.get_user", return_value={"id": "bad_id", "username": "admin"})
        def test_pydantic_return_drift(mock_get):
            services.get_user(1)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*Mockrot detected rotting mock (return_type_drift):*",
            "*Target:*services.get_user*",
            "*Input should be a valid integer*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1


def test_return_type_valid_pydantic_model_passes_in_strict(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        services="""
        from pydantic import BaseModel

        class User(BaseModel):
            id: int
            username: str

        def get_user(user_id: int) -> User:
            return User(id=user_id, username="admin")
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import services

        @patch("services.get_user", return_value={"id": 42, "username": "admin"})
        def test_pydantic_valid_mock(mock_get):
            res = services.get_user(1)
            assert res["id"] == 42
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_return_type_resilience_exception_ignored(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        network="""
        def ping_host(host: str) -> bool:
            return True
        """
    )
    pytester.makepyfile("""
        import pytest
        from unittest.mock import patch
        import network

        @patch("network.ping_host", side_effect=TimeoutError("network unreachable"))
        def test_simulated_error(mock_ping):
            with pytest.raises(TimeoutError, match="network unreachable"):
                network.ping_host("192.168.1.1")
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_unconfigured_mock_passes_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        billing="""
        def calculate_fee(amount: int) -> int:
            return amount // 10
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import billing

        @patch("billing.calculate_fee")
        def test_fee_unconfigured(mock_fee):
            fee = billing.calculate_fee(100)
            mock_fee.assert_called_once_with(100)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*1 passed*",
        ]
    )
    assert result.ret == 0
