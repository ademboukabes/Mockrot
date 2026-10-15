"""Integration tests verifying end-to-end async and AsyncMock validation (F4) with pytester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_async_mock_return_type_drift_warn_mode_reports_summary(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        orders="""
        async def fetch_order_id(order_ref: str) -> int:
            return 1001
        """
    )
    pytester.makepyfile("""
        import asyncio
        from unittest.mock import patch, AsyncMock
        import orders

        @patch("orders.fetch_order_id", new_callable=AsyncMock, return_value="1001")
        def test_order_type_drift(mock_fetch):
            async def _coro():
                order_id = await orders.fetch_order_id("ref-ABC")
                assert order_id == "1001"
            asyncio.run(_coro())
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*= Mockrot: Rotting Mocks Detected =*",
            "*[return_type_drift]*orders.fetch_order_id*",
            "*Expected: int*",
            "*Actual:*str: '1001'*",
            "*1 rotting mock(s) detected*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_async_mock_return_type_drift_strict_mode_fails_test(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        orders="""
        async def fetch_order_id(order_ref: str) -> int:
            return 1001
        """
    )
    pytester.makepyfile("""
        import asyncio
        from unittest.mock import patch, AsyncMock
        import orders

        @patch("orders.fetch_order_id", new_callable=AsyncMock, return_value="1001")
        def test_order_type_drift_strict(mock_fetch):
            async def _coro():
                await orders.fetch_order_id("ref-ABC")
            asyncio.run(_coro())
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (return_type_drift):*",
            "*Target:*orders.fetch_order_id*",
            "*Expected: int*",
            "*Actual:*str: '1001'*",
            "*1 failed*",
        ]
    )
    assert result.ret != 0


def test_async_target_mocked_synchronously_fails_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        auth="""
        async def fetch_token() -> str:
            return "real_token"
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch, Mock
        import auth

        @patch("auth.fetch_token", new_callable=Mock)
        def test_sync_mock_on_async_target(mock_token):
            mock_token.return_value = "fake_token"
            # Test called async target synchronously
            token = auth.fetch_token()
            assert token == "fake_token"
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (async_mismatch):*",
            "*Target:*auth.fetch_token*",
            "*async def / coroutine function (awaited)*",
            "*1 failed*",
        ]
    )
    assert result.ret != 0


def test_sync_target_mocked_asynchronously_fails_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        calc="""
        def add(a: int, b: int) -> int:
            return a + b
        """
    )
    pytester.makepyfile("""
        import asyncio
        from unittest.mock import patch, AsyncMock
        import calc

        @patch("calc.add", new_callable=AsyncMock, return_value=10)
        def test_async_mock_on_sync_target(mock_add):
            async def _coro():
                return await calc.add(5, 5)
            res = asyncio.run(_coro())
            assert res == 10
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (async_mismatch):*",
            "*Target:*calc.add*",
            "*Synchronous function (not awaited)*",
            "*1 failed*",
        ]
    )
    assert result.ret != 0


def test_async_mock_valid_call_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        orders="""
        from pydantic import BaseModel

        class OrderReceipt(BaseModel):
            order_id: int
            status: str

        async def create_order(item: str, quantity: int) -> OrderReceipt:
            return OrderReceipt(order_id=1, status="confirmed")
        """
    )
    pytester.makepyfile("""
        import asyncio
        from unittest.mock import patch, AsyncMock
        import orders

        @patch(
            "orders.create_order",
            new_callable=AsyncMock,
            return_value={"order_id": 99, "status": "shipped"},
        )
        def test_create_order_valid(mock_create):
            async def _coro():
                return await orders.create_order("keyboard", 2)
            receipt = asyncio.run(_coro())
            assert receipt["order_id"] == 99
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(["*1 passed*"])
    assert result.ret == 0


def test_async_mock_exception_resilience_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        network="""
        async def send_payload(payload: str) -> bool:
            return True
        """
    )
    pytester.makepyfile("""
        import asyncio
        from unittest.mock import patch, AsyncMock
        import pytest
        import network

        @patch(
            "network.send_payload",
            new_callable=AsyncMock,
            side_effect=TimeoutError("gateway timeout"),
        )
        def test_network_timeout_resilience(mock_send):
            async def _coro():
                with pytest.raises(TimeoutError, match="gateway timeout"):
                    await network.send_payload("data")
            asyncio.run(_coro())
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(["*1 passed*"])
    assert result.ret == 0
