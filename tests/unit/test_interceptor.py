"""Unit tests for transparent mock interception layer (F1)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest import mock

import _pytest.capture
import pytest

import mockrot.interceptor
from mockrot.interceptor import (
    _get_target_name,  # pyright: ignore[reportPrivateUsage]  # Unit test testing internal helper
    _is_pytest_internal,  # pyright: ignore[reportPrivateUsage]  # Unit test testing internal helper
    _wrap_plain_callable,  # pyright: ignore[reportPrivateUsage]  # Unit test testing internal helper
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


def test_intercepts_monkeypatch_async_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    async def custom_fetch(endpoint: str) -> str:
        return f"async_custom:{endpoint}"

    monkeypatch.setattr(f"{__name__}.fetch_status", custom_fetch)

    res = asyncio.run(fetch_status("/test-endpoint"))
    assert res == "async_custom:/test-endpoint"
    assert len(captured) == 1
    assert captured[0].is_async_call is True
    assert captured[0].returned_value == "async_custom:/test-endpoint"


def test_intercepts_monkeypatch_async_callable_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    async def failing_fetch(endpoint: str) -> str:
        raise ConnectionResetError(f"lost connection to {endpoint}")

    monkeypatch.setattr(f"{__name__}.fetch_status", failing_fetch)

    with pytest.raises(ConnectionResetError, match="lost connection"):
        asyncio.run(fetch_status("/broken"))

    assert len(captured) == 1
    assert captured[0].is_async_call is True
    assert isinstance(captured[0].raised_exception, ConnectionResetError)


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


class CustomCallableRecorder:
    """Callable class instance mimicking pretend.call_recorder."""

    def __init__(self, ret_val: int = 42) -> None:
        self.ret_val = ret_val
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> int:
        self.calls.append((args, kwargs))
        return self.ret_val


def test_monkeypatch_callable_instance_preserves_custom_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    service = OrderService()
    recorder = CustomCallableRecorder(ret_val=99)

    monkeypatch.setattr(service, "calculate_discount", recorder)

    res = service.calculate_discount(0.2)
    assert res == 99
    # Behavioral transparency invariant: custom attributes like .calls must be preserved
    assert len(recorder.calls) == 1
    assert recorder.calls[0][0] == (0.2,)


class MockDataSource:
    def __init__(self, data: str) -> None:
        self.data = data

    def fetch_data(self) -> str:
        return self.data


class ConsumerService:
    def get_content(self) -> str:
        return "default"


def test_monkeypatch_class_attribute_with_bound_method_preserves_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    source = MockDataSource("hello from source")
    # Patch ConsumerService.get_content with bound method source.fetch_data
    monkeypatch.setattr(ConsumerService, "get_content", source.fetch_data)

    consumer = ConsumerService()
    # Must not raise TypeError: consumer must not be passed to source.fetch_data
    assert consumer.get_content() == "hello from source"


def test_interceptor_ignores_pytest_internal_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    def fake_read(*_args: Any, **_kwargs: Any) -> str:
        return "mocked"

    fake_stream = _pytest.capture.DontReadFromInput()
    monkeypatch.setattr(fake_stream, "read", fake_read)

    assert fake_stream.read() == "mocked"
    # Pytest internal targets must never be recorded or validated
    assert len(captured) == 0


def test_wrap_plain_callable_preserves_metadata_and_idempotency() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    def sample_func(x: int) -> int:
        """Sample docstring."""
        return x * 2

    def orig_sample(x: int) -> int:
        return x

    wrapped = _wrap_plain_callable(sample_func, orig_sample, "sample_func")
    assert wrapped.__name__ == "sample_func"
    assert wrapped.__doc__ == "Sample docstring."

    # Idempotent: wrapping again returns the exact same wrapper
    wrapped_again = _wrap_plain_callable(wrapped, orig_sample, "sample_func")
    assert wrapped_again is wrapped


def test_is_pytest_internal_handles_none_and_non_pytest() -> None:
    assert _is_pytest_internal(None) is False
    assert _is_pytest_internal(compute_total) is False


def test_dotted_monkeypatch_target_wrapping(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    def dummy_compute(price: int, tax: int) -> int:
        return price + tax + 100

    monkeypatch.setattr(f"{__name__}.compute_total", dummy_compute)
    res = compute_total(5, 5)
    assert res == 110
    assert len(captured) == 1
    assert captured[0].args == (5, 5)
    assert captured[0].returned_value == 110


def test_uninstall_interceptor_idempotent() -> None:
    uninstall_interceptor()
    # Calling uninstall again when not installed should be a no-op
    uninstall_interceptor()
    assert is_interceptor_installed() is False


def test_get_target_name_without_attribute() -> None:
    name = _get_target_name(compute_total, "")
    assert "compute_total" in name


def test_interceptor_skips_patch_on_pytest_itself() -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    with mock.patch.object(pytest, "skip") as mock_skip:
        mock_skip.return_value = None
        # Target module is pytest, so mockrot should not wrap or record it
        pytest.skip("skipping")

    assert len(captured) == 0


def test_interceptor_skips_monkeypatch_on_pytest_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    orig_skip = pytest.skip
    monkeypatch.setattr(pytest, "skip", orig_skip)
    assert pytest.skip is orig_skip
    assert len(captured) == 0


def test_wrap_plain_callable_skips_pytest_internal_orig_target() -> None:
    def sample_fn() -> str:
        return "ok"

    assert (
        _wrap_plain_callable(sample_fn, _pytest.capture.DontReadFromInput.read, "read") is sample_fn
    )


def test_monkeypatch_replacement_with_mock_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[MockInteraction] = []
    install_interceptor(captured.append)

    service = OrderService()
    m = mock.MagicMock(return_value=123.0)
    monkeypatch.setattr(service, "calculate_discount", m)

    res = service.calculate_discount(0.1)
    assert res == 123.0
    assert len(captured) == 1
    assert captured[0].returned_value == 123.0
