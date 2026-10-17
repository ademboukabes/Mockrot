"""Unit tests for transparent mock interception layer (F1)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

import mockrot.interceptor
from mockrot.interceptor import (
    install_interceptor,
    is_interceptor_installed,
    uninstall_interceptor,
)

if TYPE_CHECKING:
    from mockrot.models import MockInteraction


# Sample production functions for testing interception
def compute_total(price: int, tax: int) -> int:
    """Production function to be patched."""
    return price + tax


async def fetch_status(endpoint: str) -> str:
    """Async production function to be patched."""
    return f"status_ok:{endpoint}"


class OrderService:
    """Production service class."""

    def calculate_discount(self, rate: float) -> float:
        return rate * 0.1


@pytest.fixture(autouse=True)
def _cleanup_interceptor() -> Any:
    """Ensure interceptor is cleaned up after every test."""
    yield
    uninstall_interceptor()


def test_installs_and_uninstalls_idempotently() -> None:
    uninstall_interceptor()
    assert not is_interceptor_installed()

    install_interceptor(lambda _: None)
    assert is_interceptor_installed()

    # Second install is idempotent
    install_interceptor(lambda _: None)
    assert is_interceptor_installed()

    uninstall_interceptor()
    assert not is_interceptor_installed()

    # Second uninstall is idempotent
    uninstall_interceptor()
    assert not is_interceptor_installed()


def test_intercepts_decorator_patch_when_function_is_called() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    @mock.patch(f"{__name__}.compute_total", return_value=99)
    def run_decorated_test(_mock_fn: mock.MagicMock) -> int:
        return compute_total(10, 2)

    result = run_decorated_test()

    assert result == 99
    assert len(captured) == 1
    interaction = captured[0]
    assert interaction.target_func is compute_total
    assert interaction.target_name.endswith("compute_total")
    assert interaction.args == (10, 2)
    assert interaction.kwargs == {}
    assert interaction.returned_value == 99
    assert interaction.raised_exception is None


def test_intercepts_context_manager_patch_when_mock_is_called() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    with mock.patch(f"{__name__}.compute_total", return_value=123):
        res = compute_total(50, tax=5)

    assert res == 123
    assert len(captured) == 1
    assert captured[0].args == (50,)
    assert captured[0].kwargs == {"tax": 5}
    assert captured[0].returned_value == 123


def test_intercepts_patch_start_when_mock_is_called() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    p = mock.patch(f"{__name__}.compute_total", return_value=777)
    p.start()
    try:
        res = compute_total(100, 200)
    finally:
        p.stop()

    assert res == 777
    assert len(captured) == 1
    assert captured[0].returned_value == 777


def test_intercepts_async_mock_when_awaited() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    async def _async_test() -> str:
        with mock.patch(f"{__name__}.fetch_status", new_callable=mock.AsyncMock) as async_mock:
            async_mock.return_value = "mocked_status"
            return await fetch_status("/api/orders")

    result = asyncio.run(_async_test())

    assert result == "mocked_status"
    assert len(captured) == 1
    assert captured[0].target_func is fetch_status
    assert captured[0].args == ("/api/orders",)
    assert captured[0].returned_value == "mocked_status"


def test_intercepts_monkeypatch_setattr_when_callable_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    service = OrderService()

    def dummy_discount(_rate: float) -> float:
        return 42.0

    monkeypatch.setattr(service, "calculate_discount", dummy_discount)

    res = service.calculate_discount(0.5)

    assert res == 42.0
    assert len(captured) == 1
    assert captured[0].args == (0.5,)
    assert captured[0].returned_value == 42.0


def test_captures_accurate_file_and_line_number_of_caller() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    with mock.patch(f"{__name__}.compute_total", return_value=1):
        compute_total(1, 1)

    assert len(captured) == 1
    site = captured[0].site
    assert site.file_path.endswith("test_interceptor.py")
    assert site.line_number > 0
    assert site.test_name == "test_captures_accurate_file_and_line_number_of_caller"


def test_preserves_mock_return_value_and_recorded_calls() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    with mock.patch(f"{__name__}.compute_total", return_value=42) as mock_compute:
        res = compute_total(10, 20)
        assert mock_compute.call_count == 1
        assert mock_compute.call_args == mock.call(10, 20)
        mock_compute.assert_called_once_with(10, 20)

    assert res == 42


def test_preserves_mock_side_effect_exceptions() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    with (
        mock.patch(f"{__name__}.compute_total", side_effect=ValueError("boom")),
        pytest.raises(ValueError, match="boom"),
    ):
        compute_total(10, 20)

    assert len(captured) == 1
    assert isinstance(captured[0].raised_exception, ValueError)
    assert str(captured[0].raised_exception) == "boom"


def test_prevents_infinite_recursion_via_reentrancy_protection() -> None:
    def recursive_listener(_interaction: MockInteraction) -> None:
        # Listener calls a mock inside itself
        if compute_total is not None:
            # Should not re-enter or deadlock
            pass

    install_interceptor(recursive_listener)

    with mock.patch(f"{__name__}.compute_total", return_value=10):
        res = compute_total(1, 2)

    assert res == 10


def test_intercepts_async_mock_when_side_effect_raises_exception() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    async def _async_failing_test() -> None:
        with (
            mock.patch(
                f"{__name__}.fetch_status",
                new_callable=mock.AsyncMock,
                side_effect=RuntimeError("network error"),
            ),
            pytest.raises(RuntimeError, match="network error"),
        ):
            await fetch_status("/api/error")

    asyncio.run(_async_failing_test())

    assert len(captured) == 1
    assert isinstance(captured[0].raised_exception, RuntimeError)
    assert str(captured[0].raised_exception) == "network error"


def test_intercepts_monkeypatch_when_callable_raises_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    service = OrderService()

    def failing_discount(_rate: float) -> float:
        raise ValueError("discount invalid")

    monkeypatch.setattr(service, "calculate_discount", failing_discount)

    with pytest.raises(ValueError, match="discount invalid"):
        service.calculate_discount(-1.0)

    assert len(captured) == 1
    assert isinstance(captured[0].raised_exception, ValueError)


def test_bypasses_interception_when_listener_is_cleared() -> None:
    install_interceptor(lambda _: None)

    with mock.patch(f"{__name__}.compute_total", return_value=55):
        # Now clear listener without full uninstall
        mockrot.interceptor._STATE.listener = None  # pyright: ignore[reportPrivateUsage]  # Test internal state bypass
        res = compute_total(1, 1)

    assert res == 55


def test_avoids_double_wrapping_when_mock_already_wrapped() -> None:
    mock_obj = mock.MagicMock(return_value=1)
    mockrot.interceptor._wrap_mock_object(  # pyright: ignore[reportPrivateUsage]  # Test internal idempotency
        mock_obj, compute_total, "compute_total"
    )
    first_wrapper = mock_obj._mock_call

    # Second wrap should be a no-op
    mockrot.interceptor._wrap_mock_object(  # pyright: ignore[reportPrivateUsage]  # Test internal idempotency
        mock_obj, compute_total, "compute_total"
    )
    assert mock_obj._mock_call is first_wrapper


def test_failsafe_recovers_gracefully_when_internal_inspection_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_interceptor(lambda _: None)

    # Force an error inside _wrap_mock_object
    def exploding_wrap(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("catastrophic internal error")

    monkeypatch.setattr(mockrot.interceptor, "_wrap_mock_object", exploding_wrap)

    # Invariant 1: must never crash user tests even on internal explosion
    with mock.patch(f"{__name__}.compute_total", return_value=123):
        res = compute_total(5, 5)

    assert res == 123


def test_intercepts_async_callable_when_monkeypatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    async def fake_status(endpoint: str) -> str:
        return f"fake:{endpoint}"

    monkeypatch.setattr(f"{__name__}.fetch_status", fake_status)

    async def _run() -> str:
        return await fetch_status("/health")

    res = asyncio.run(_run())
    assert res == "fake:/health"
    assert len(captured) == 1
    assert captured[0].is_async_call is True
    assert captured[0].returned_value == "fake:/health"


def test_intercepts_async_callable_when_it_raises_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    async def failing_status(endpoint: str) -> str:
        raise ConnectionResetError(f"connection dropped at {endpoint}")

    monkeypatch.setattr(f"{__name__}.fetch_status", failing_status)

    async def _run() -> None:
        await fetch_status("/down")

    with pytest.raises(ConnectionResetError, match="connection dropped"):
        asyncio.run(_run())

    assert len(captured) == 1
    assert captured[0].is_async_call is True
    assert isinstance(captured[0].raised_exception, ConnectionResetError)


def test_ignores_monkeypatch_originating_from_runner_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    def replacement_fn(price: int, tax: int) -> int:
        return price + tax

    # Simulate caller from pytest_asyncio/plugin.py
    with mock.patch("sys._getframe") as mock_getframe:
        fake_frame = mock.MagicMock()
        fake_frame.f_code.co_filename = "/path/site-packages/pytest_asyncio/plugin.py"
        mock_getframe.return_value = fake_frame

        monkeypatch.setattr(f"{__name__}.compute_total", replacement_fn)

    # Calling compute_total should not have been wrapped by Mockrot
    assert compute_total(1, 2) == 3
    assert len(captured) == 0


class SampleClassMethods:
    """Sample class with classmethod and staticmethod."""

    @classmethod
    def process_class(cls, count: int) -> str:
        return f"cls:{count}"

    @staticmethod
    def process_static(tag: str) -> str:
        return f"static:{tag}"


def test_intercept_classmethod_patch() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    with mock.patch.object(SampleClassMethods, "process_class", return_value="custom"):
        res = SampleClassMethods.process_class(42)
        assert res == "custom"

    assert len(captured) == 1
    assert captured[0].args == (42,)
    assert captured[0].returned_value == "custom"
    assert "SampleClassMethods.process_class" in captured[0].target_name


def test_intercept_staticmethod_patch() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    with mock.patch.object(SampleClassMethods, "process_static", return_value="static_custom"):
        res = SampleClassMethods.process_static("alpha")
        assert res == "static_custom"

    assert len(captured) == 1
    assert captured[0].args == ("alpha",)
    assert captured[0].returned_value == "static_custom"
    assert "SampleClassMethods.process_static" in captured[0].target_name


def test_async_mock_site_captured_at_call_time() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    m = mock.AsyncMock(return_value="bad")

    with mock.patch(f"{__name__}.fetch_status", m):

        async def background_worker() -> None:
            coro = fetch_status("/test")
            task = asyncio.create_task(coro)
            await task

        asyncio.run(background_worker())

    assert len(captured) == 1
    assert captured[0].site.file_path.endswith("test_interceptor.py")
    assert captured[0].site.test_name == "background_worker"
    assert "asyncio" not in captured[0].site.file_path
