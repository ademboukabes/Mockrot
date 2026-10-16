"""Transparent mock interception layer for unittest.mock and pytest.MonkeyPatch."""

from __future__ import annotations

import inspect
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest import mock

from mockrot.models import MockInteraction, MockSite

try:
    import _pytest.monkeypatch as _mp
except ImportError:  # pragma: no cover
    _mp = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import _pytest.monkeypatch

# Type alias for listener callback receiving intercepted interactions
InteractionListener = Callable[[MockInteraction], None]


@dataclass
class _InterceptorState:
    """Internal state tracking original patch methods and active listener."""

    orig_patch_enter: Callable[..., Any] | None = None
    orig_monkeypatch_setattr: Callable[..., Any] | None = None
    listener: InteractionListener | None = None
    is_installed: bool = False


_STATE = _InterceptorState()

# Thread-local storage to prevent reentrant interception loops
_TLS = threading.local()


def _is_active() -> bool:
    """Return True if currently processing an interception."""
    return bool(getattr(_TLS, "active", False))


def _resolve_mock_site() -> MockSite:
    """Resolve caller file, line, and test name, skipping internal frameworks."""
    try:
        # sys._getframe is used for fast memory-only frame traversal without blocking disk I/O
        frame = sys._getframe(1)  # pyright: ignore[reportPrivateUsage] - fast frame inspection
        while frame is not None:
            fn = frame.f_code.co_filename
            if any(
                skip in fn
                for skip in (
                    "unittest/mock.py",
                    "contextlib.py",
                    "_pytest",
                    "/mockrot/",
                    "pluggy",
                    "pytest_asyncio",
                )
            ):
                frame = frame.f_back
                continue
            return MockSite(
                file_path=fn,
                line_number=frame.f_lineno,
                test_name=frame.f_code.co_name,
            )
    except (AttributeError, ValueError):
        pass
    return MockSite(file_path="unknown", line_number=0, test_name="")


def _get_target_name(target: Any, attribute: str | None = None) -> str:
    """Build a human-readable identifier for the target function or attribute."""
    if attribute:
        target_mod = getattr(target, "__module__", "")
        target_cls = getattr(target, "__name__", "")
        prefix = (
            f"{target_mod}.{target_cls}" if target_mod and target_cls else target_cls or target_mod
        )
        return f"{prefix}.{attribute}" if prefix else attribute

    module = getattr(target, "__module__", "")
    qualname = getattr(target, "__qualname__", getattr(target, "__name__", str(target)))
    return f"{module}.{qualname}" if module else qualname


def _wrap_mock_object(mock_obj: Any, orig_target: Any, target_name: str) -> None:
    """Wrap the _mock_call dispatch of a Mock or AsyncMock instance."""
    if not hasattr(mock_obj, "_mock_call"):
        return

    orig_mock_call = mock_obj._mock_call
    if getattr(orig_mock_call, "__mockrot_wrapped__", False):
        return

    is_async = isinstance(mock_obj, mock.AsyncMock)

    if is_async:

        async def async_interceptor_wrapper(*args: Any, **kwargs: Any) -> Any:
            if _is_active() or _STATE.listener is None:
                return await orig_mock_call(*args, **kwargs)

            _TLS.active = True
            try:
                site = _resolve_mock_site()
                try:
                    result = await orig_mock_call(*args, **kwargs)
                except BaseException as exc:
                    _STATE.listener(
                        MockInteraction(
                            site=site,
                            target_func=orig_target,
                            target_name=target_name,
                            args=args,
                            kwargs=kwargs,
                            returned_value=None,
                            raised_exception=exc,
                            is_async_call=True,
                        )
                    )
                    raise
                else:
                    _STATE.listener(
                        MockInteraction(
                            site=site,
                            target_func=orig_target,
                            target_name=target_name,
                            args=args,
                            kwargs=kwargs,
                            returned_value=result,
                            raised_exception=None,
                            is_async_call=True,
                        )
                    )
                    return result
            finally:
                _TLS.active = False

        async_interceptor_wrapper.__mockrot_wrapped__ = True  # type: ignore[attr-defined]
        mock_obj._mock_call = async_interceptor_wrapper

    else:

        def sync_interceptor_wrapper(*args: Any, **kwargs: Any) -> Any:
            if _is_active() or _STATE.listener is None:
                return orig_mock_call(*args, **kwargs)

            _TLS.active = True
            try:
                site = _resolve_mock_site()
                try:
                    result = orig_mock_call(*args, **kwargs)
                except BaseException as exc:
                    _STATE.listener(
                        MockInteraction(
                            site=site,
                            target_func=orig_target,
                            target_name=target_name,
                            args=args,
                            kwargs=kwargs,
                            returned_value=None,
                            raised_exception=exc,
                            is_async_call=False,
                        )
                    )
                    raise
                else:
                    _STATE.listener(
                        MockInteraction(
                            site=site,
                            target_func=orig_target,
                            target_name=target_name,
                            args=args,
                            kwargs=kwargs,
                            returned_value=result,
                            raised_exception=None,
                            is_async_call=False,
                        )
                    )
                    return result
            finally:
                _TLS.active = False

        sync_interceptor_wrapper.__mockrot_wrapped__ = True  # type: ignore[attr-defined]
        mock_obj._mock_call = sync_interceptor_wrapper


def _wrap_plain_callable(func: Any, orig_target: Any, target_name: str) -> Any:
    """Wrap a non-Mock callable (e.g. lambda or dummy function) with interception."""
    if getattr(func, "__mockrot_wrapped__", False):
        return func

    if inspect.iscoroutinefunction(func):

        async def async_callable_wrapper(*args: Any, **kwargs: Any) -> Any:
            if _is_active() or _STATE.listener is None:
                return await func(*args, **kwargs)

            _TLS.active = True
            try:
                site = _resolve_mock_site()
                try:
                    result = await func(*args, **kwargs)
                except BaseException as exc:
                    _STATE.listener(
                        MockInteraction(
                            site=site,
                            target_func=orig_target,
                            target_name=target_name,
                            args=args,
                            kwargs=kwargs,
                            returned_value=None,
                            raised_exception=exc,
                            is_async_call=True,
                        )
                    )
                    raise
                else:
                    _STATE.listener(
                        MockInteraction(
                            site=site,
                            target_func=orig_target,
                            target_name=target_name,
                            args=args,
                            kwargs=kwargs,
                            returned_value=result,
                            raised_exception=None,
                            is_async_call=True,
                        )
                    )
                    return result
            finally:
                _TLS.active = False

        async_callable_wrapper.__mockrot_wrapped__ = True  # type: ignore[attr-defined]
        return async_callable_wrapper

    def callable_wrapper(*args: Any, **kwargs: Any) -> Any:
        if _is_active() or _STATE.listener is None:
            return func(*args, **kwargs)

        _TLS.active = True
        try:
            site = _resolve_mock_site()
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                _STATE.listener(
                    MockInteraction(
                        site=site,
                        target_func=orig_target,
                        target_name=target_name,
                        args=args,
                        kwargs=kwargs,
                        returned_value=None,
                        raised_exception=exc,
                        is_async_call=False,
                    )
                )
                raise
            else:
                _STATE.listener(
                    MockInteraction(
                        site=site,
                        target_func=orig_target,
                        target_name=target_name,
                        args=args,
                        kwargs=kwargs,
                        returned_value=result,
                        raised_exception=None,
                        is_async_call=False,
                    )
                )
                return result
        finally:
            _TLS.active = False

    callable_wrapper.__mockrot_wrapped__ = True  # type: ignore[attr-defined]
    return callable_wrapper


def _patched_enter(patch_self: Any) -> Any:
    """Intercept unittest.mock._patch.__enter__ to wrap created mocks transparently."""
    if _STATE.orig_patch_enter is None:
        return patch_self  # pragma: no cover

    mock_obj = _STATE.orig_patch_enter(patch_self)

    try:
        orig_target = getattr(patch_self, "temp_original", None)
        attr_name = getattr(patch_self, "attribute", "")
        target_obj = getattr(patch_self, "target", None)
        target_name = _get_target_name(target_obj, attr_name)

        if callable(orig_target) and hasattr(mock_obj, "_mock_call"):
            _wrap_mock_object(mock_obj, orig_target, target_name)
    except Exception:  # noqa: BLE001
        # Invariant 1: fail-safe, never crash user tests on internal interception failure
        pass

    return mock_obj


def _is_runner_internal_caller() -> bool:
    """Return True if caller of monkeypatch is an internal test runner or plugin."""
    try:
        caller = sys._getframe(2)  # pyright: ignore[reportPrivateUsage] - caller inspection
        caller_fn = caller.f_code.co_filename
        return any(skip in caller_fn for skip in ("pytest_asyncio", "_pytest", "pluggy"))
    except (AttributeError, ValueError):
        return False


def _wrap_dotted_monkeypatch(target: str, value: Any) -> Any:
    """Wrap replacement mock or callable when monkeypatch uses dotted target string."""
    if "." not in target:
        return value
    mod_name, attr = target.rsplit(".", 1)
    try:
        mod = sys.modules.get(mod_name) or __import__(mod_name, fromlist=[attr])
        orig_target = getattr(mod, attr, None)
        if hasattr(value, "_mock_call"):
            _wrap_mock_object(value, orig_target, target)
        elif callable(value) and callable(orig_target):
            return _wrap_plain_callable(value, orig_target, target)
    except Exception:  # noqa: BLE001
        pass
    return value


def _patched_monkeypatch_setattr(
    self: _pytest.monkeypatch.MonkeyPatch,
    target: str | object,
    name: object | str = mock.DEFAULT,
    value: object = mock.DEFAULT,
    raising: bool = True,
) -> None:
    """Intercept pytest.MonkeyPatch.setattr to wrap replacement callables or mocks."""
    if _STATE.orig_monkeypatch_setattr is None:
        return  # pragma: no cover

    if _is_active():
        _STATE.orig_monkeypatch_setattr(self, target, name, value, raising=raising)
        return

    _TLS.active = True
    try:
        if _is_runner_internal_caller():
            if value is mock.DEFAULT:
                _STATE.orig_monkeypatch_setattr(self, target, name, raising=raising)
            else:
                _STATE.orig_monkeypatch_setattr(self, target, name, value, raising=raising)
            return

        if value is mock.DEFAULT:
            real_name = _wrap_dotted_monkeypatch(target, name) if isinstance(target, str) else name
            _STATE.orig_monkeypatch_setattr(self, target, real_name, raising=raising)
            return

        if isinstance(name, str):
            orig_target = getattr(target, name, None)
            target_name = _get_target_name(target, name)
            if hasattr(value, "_mock_call"):
                _wrap_mock_object(value, orig_target, target_name)
            elif callable(value) and callable(orig_target):
                value = _wrap_plain_callable(value, orig_target, target_name)

        _STATE.orig_monkeypatch_setattr(self, target, name, value, raising=raising)
    finally:
        _TLS.active = False


def is_interceptor_installed() -> bool:
    """Return True if mockrot interceptor is actively installed."""
    return _STATE.is_installed


def install_interceptor(listener: InteractionListener) -> None:
    """Install interception hooks on unittest.mock._patch and MonkeyPatch.setattr."""
    _STATE.listener = listener
    if _STATE.is_installed:
        return

    patch_cls: Any = mock._patch  # pyright: ignore[reportPrivateUsage]  # Wrap unittest.mock._patch.__enter__
    _STATE.orig_patch_enter = patch_cls.__enter__
    patch_cls.__enter__ = _patched_enter

    if _mp is not None and hasattr(_mp, "MonkeyPatch"):
        _STATE.orig_monkeypatch_setattr = _mp.MonkeyPatch.setattr
        _mp.MonkeyPatch.setattr = _patched_monkeypatch_setattr  # type: ignore[assignment]

    _STATE.is_installed = True


def uninstall_interceptor() -> None:
    """Restore original patch methods idempotently."""
    if not _STATE.is_installed:
        return

    if _STATE.orig_patch_enter is not None:
        patch_cls: Any = mock._patch  # pyright: ignore[reportPrivateUsage]  # Restore original _patch.__enter__
        patch_cls.__enter__ = _STATE.orig_patch_enter
        _STATE.orig_patch_enter = None

    if _STATE.orig_monkeypatch_setattr is not None:
        if _mp is not None and hasattr(_mp, "MonkeyPatch"):
            _mp.MonkeyPatch.setattr = _STATE.orig_monkeypatch_setattr  # type: ignore[assignment]
        _STATE.orig_monkeypatch_setattr = None

    _STATE.listener = None
    _STATE.is_installed = False
