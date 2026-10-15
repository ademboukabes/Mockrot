"""Transparent mock interception layer for unittest.mock and pytest.MonkeyPatch."""

from __future__ import annotations

import inspect
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
    stack = inspect.stack()
    # Skip inspect and interceptor frames
    for frame_info in stack[2:]:
        fn = frame_info.filename
        if any(
            skip in fn for skip in ("unittest/mock.py", "contextlib.py", "_pytest", "/mockrot/")
        ):
            continue
        return MockSite(
            file_path=frame_info.filename,
            line_number=frame_info.lineno,
            test_name=frame_info.function,
        )
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

            site = _resolve_mock_site()
            _TLS.active = True
            try:
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

            site = _resolve_mock_site()
            _TLS.active = True
            try:
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

    def callable_wrapper(*args: Any, **kwargs: Any) -> Any:
        if _is_active() or _STATE.listener is None:
            return func(*args, **kwargs)

        site = _resolve_mock_site()
        _TLS.active = True
        try:
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

    # Resolve target and attribute according to MonkeyPatch.setattr semantics
    real_target = target
    real_name = name
    real_value = value

    try:
        if real_value is mock.DEFAULT:
            # Dotted import path style handled directly
            pass
        elif isinstance(real_name, str):
            orig_target = getattr(real_target, real_name, None)
            target_name = _get_target_name(real_target, real_name)

            if hasattr(real_value, "_mock_call"):
                _wrap_mock_object(real_value, orig_target, target_name)
            elif callable(real_value) and callable(orig_target):
                real_value = _wrap_plain_callable(real_value, orig_target, target_name)
    except Exception:  # noqa: BLE001
        pass

    _STATE.orig_monkeypatch_setattr(self, real_target, real_name, real_value, raising)


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
