"""Transparent mock interception layer for unittest.mock and pytest.MonkeyPatch."""

from __future__ import annotations

import functools
import inspect
import sys
import threading
import types
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


def _is_pytest_internal(target: Any) -> bool:
    """Return True if target or its module belongs to pytest internal machinery."""
    if target is None:
        return False
    mod = getattr(target, "__module__", "") or ""
    return mod.startswith(("_pytest", "pytest"))


_SKIP_MODULE_PREFIXES: tuple[str, ...] = (
    "unittest.mock",
    "contextlib",
    "_pytest",
    "pluggy",
    "pytest_asyncio",
    "asyncio",
    "concurrent.futures",
    "mockrot",
)


def _resolve_mock_site() -> MockSite:
    """Resolve caller file, line, and test name, skipping internal frameworks."""
    try:
        # sys._getframe is used for fast memory-only frame traversal without blocking disk I/O
        frame = sys._getframe(1)  # pyright: ignore[reportPrivateUsage] - fast frame inspection
        while frame is not None:
            mod_name = frame.f_globals.get("__name__", "")
            if any(
                mod_name == skip or mod_name.startswith(f"{skip}.")
                for skip in _SKIP_MODULE_PREFIXES
            ):
                frame = frame.f_back
                continue
            return MockSite(
                file_path=frame.f_code.co_filename,
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

    if _is_pytest_internal(orig_target):
        return

    orig_mock_call = mock_obj._mock_call
    if getattr(orig_mock_call, "__mockrot_wrapped__", False):
        return

    is_async = isinstance(mock_obj, mock.AsyncMock)

    if is_async:

        def async_interceptor_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Capture site synchronously at the exact moment mock() is invoked by caller
            site = _resolve_mock_site()

            async def _execute_and_validate() -> Any:
                if _is_active() or _STATE.listener is None:
                    return await orig_mock_call(*args, **kwargs)

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

            return _execute_and_validate()

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
    # Only wrap user-defined Python functions (FunctionType).
    # Leave callable class instances (e.g. pretend.call_recorder), bound methods,
    # builtins, and partials untouched to preserve method binding and custom attributes.
    if type(func) is not types.FunctionType:
        return func

    if getattr(func, "__mockrot_wrapped__", False):
        return func

    if _is_pytest_internal(orig_target):
        return func

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
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

    @functools.wraps(func)
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


# Preserve true original unpatched standard library functions across reloads/patches
_orig_patch: Any = (
    getattr(mock, "_mockrot_original_patch_enter", None) or getattr(mock._patch, "__enter__")  # noqa: B009 # pyright: ignore[reportPrivateUsage]
)
_ORIGINAL_PATCH_ENTER: Callable[..., Any] = _orig_patch
setattr(mock, "_mockrot_original_patch_enter", _ORIGINAL_PATCH_ENTER)  # noqa: B010

_orig_monkeypatch: Callable[..., Any] | None = None
if _mp is not None and hasattr(_mp, "MonkeyPatch"):
    _orig_monkeypatch = (
        getattr(_mp, "_mockrot_original_monkeypatch_setattr", None) or _mp.MonkeyPatch.setattr
    )
    setattr(_mp, "_mockrot_original_monkeypatch_setattr", _orig_monkeypatch)  # noqa: B010
_ORIGINAL_MONKEYPATCH_SETATTR: Callable[..., Any] | None = _orig_monkeypatch


def _unwrap_descriptor(target: Any) -> Any:
    """Extract underlying callable from classmethod or staticmethod descriptor."""
    if type(target) in (classmethod, staticmethod):
        return getattr(target, "__func__", target)
    return target


def _patched_enter(patch_self: Any) -> Any:
    """Intercept unittest.mock._patch.__enter__ to wrap created mocks transparently."""
    enter_fn = _STATE.orig_patch_enter
    if enter_fn is None or getattr(enter_fn, "__mockrot_wrapper__", False):
        enter_fn = _ORIGINAL_PATCH_ENTER

    mock_obj = enter_fn(patch_self)

    try:
        target_obj = getattr(patch_self, "target", None)
        if _is_pytest_internal(target_obj):
            return mock_obj
        orig_target: Any = _unwrap_descriptor(getattr(patch_self, "temp_original", None))
        if _is_pytest_internal(orig_target):
            return mock_obj
        attr_name = getattr(patch_self, "attribute", "")
        target_name = _get_target_name(target_obj, attr_name)

        if callable(orig_target) and hasattr(mock_obj, "_mock_call"):
            _wrap_mock_object(mock_obj, orig_target, target_name)
    except Exception:  # noqa: BLE001
        # Invariant 1: fail-safe, never crash user tests on internal interception failure
        pass

    return mock_obj


_patched_enter.__mockrot_wrapper__ = True  # type: ignore[attr-defined]


def _is_runner_internal_caller() -> bool:
    """Return True if caller of monkeypatch is an internal test runner or plugin."""
    try:
        caller = sys._getframe(2)  # pyright: ignore[reportPrivateUsage] - caller inspection
        mod_name = caller.f_globals.get("__name__", "")
        return any(
            mod_name == skip or mod_name.startswith(f"{skip}.")
            for skip in ("pytest_asyncio", "_pytest", "pluggy")
        )
    except (AttributeError, ValueError):
        return False


def _wrap_dotted_monkeypatch(target: str, value: Any) -> Any:
    """Wrap replacement mock or callable when monkeypatch uses dotted target string."""
    if "." not in target or target.startswith(("_pytest.", "pytest.")):
        return value
    mod_name, attr = target.rsplit(".", 1)
    try:
        mod = sys.modules.get(mod_name) or __import__(mod_name, fromlist=[attr])
        orig_target: Any = _unwrap_descriptor(getattr(mod, attr, None))
        if _is_pytest_internal(orig_target):
            return value
        if hasattr(value, "_mock_call"):
            _wrap_mock_object(value, orig_target, target)
        elif callable(value) and callable(orig_target):
            return _wrap_plain_callable(value, orig_target, target)
    except Exception:  # noqa: BLE001
        pass
    return value


def _wrap_monkeypatch_replacement(target: object, name: str, value: Any) -> Any:
    """Wrap a replacement mock or callable passed to monkeypatch.setattr."""
    if _is_pytest_internal(target):
        return value
    raw_target = inspect.getattr_static(target, name, None)
    if raw_target is None:
        raw_target = getattr(target, name, None)
    if _is_pytest_internal(raw_target):
        return value
    orig_target: Any = _unwrap_descriptor(raw_target)
    target_name = _get_target_name(target, name)
    if hasattr(value, "_mock_call"):
        _wrap_mock_object(value, orig_target, target_name)
    elif callable(value) and callable(orig_target):
        return _wrap_plain_callable(value, orig_target, target_name)
    return value


def _patched_monkeypatch_setattr(
    self: _pytest.monkeypatch.MonkeyPatch,
    target: str | object,
    name: object | str = mock.DEFAULT,
    value: object = mock.DEFAULT,
    raising: bool = True,
) -> None:
    """Intercept pytest.MonkeyPatch.setattr to wrap replacement callables or mocks."""
    setattr_fn = _STATE.orig_monkeypatch_setattr
    if setattr_fn is None or getattr(setattr_fn, "__mockrot_wrapper__", False):
        setattr_fn = _ORIGINAL_MONKEYPATCH_SETATTR
    if setattr_fn is None:
        return  # pragma: no cover

    if _is_active():
        setattr_fn(self, target, name, value, raising=raising)
        return

    _TLS.active = True
    try:
        if _is_runner_internal_caller():
            if value is mock.DEFAULT:
                setattr_fn(self, target, name, raising=raising)
            else:
                setattr_fn(self, target, name, value, raising=raising)
            return

        if value is mock.DEFAULT:
            real_name = _wrap_dotted_monkeypatch(target, name) if isinstance(target, str) else name
            setattr_fn(self, target, real_name, raising=raising)
            return

        if isinstance(name, str):
            value = _wrap_monkeypatch_replacement(target, name, value)

        setattr_fn(self, target, name, value, raising=raising)
    finally:
        _TLS.active = False


_patched_monkeypatch_setattr.__mockrot_wrapper__ = True  # type: ignore[attr-defined]


def is_interceptor_installed() -> bool:
    """Return True if mockrot interceptor is actively installed."""
    return _STATE.is_installed


def install_interceptor(listener: InteractionListener) -> None:
    """Install interception hooks on unittest.mock._patch and MonkeyPatch.setattr."""
    _STATE.listener = listener
    if _STATE.is_installed:
        return

    patch_cls: Any = mock._patch  # pyright: ignore[reportPrivateUsage]  # Wrap unittest.mock._patch.__enter__
    if not getattr(patch_cls.__enter__, "__mockrot_wrapper__", False):
        _STATE.orig_patch_enter = patch_cls.__enter__
    elif _STATE.orig_patch_enter is None:
        _STATE.orig_patch_enter = _ORIGINAL_PATCH_ENTER
    patch_cls.__enter__ = _patched_enter

    if _mp is not None and hasattr(_mp, "MonkeyPatch"):
        if not getattr(_mp.MonkeyPatch.setattr, "__mockrot_wrapper__", False):
            _STATE.orig_monkeypatch_setattr = _mp.MonkeyPatch.setattr
        elif _STATE.orig_monkeypatch_setattr is None:
            _STATE.orig_monkeypatch_setattr = _ORIGINAL_MONKEYPATCH_SETATTR
        _mp.MonkeyPatch.setattr = _patched_monkeypatch_setattr  # type: ignore[assignment]

    _STATE.is_installed = True


def uninstall_interceptor() -> None:
    """Restore original patch methods idempotently."""
    if not _STATE.is_installed:
        return

    patch_cls: Any = mock._patch  # pyright: ignore[reportPrivateUsage]  # Restore original _patch.__enter__
    restore_enter = _STATE.orig_patch_enter
    if restore_enter is None or getattr(restore_enter, "__mockrot_wrapper__", False):
        restore_enter = _ORIGINAL_PATCH_ENTER
    patch_cls.__enter__ = restore_enter
    _STATE.orig_patch_enter = None

    if _mp is not None and hasattr(_mp, "MonkeyPatch"):
        restore_setattr = _STATE.orig_monkeypatch_setattr
        if restore_setattr is None or getattr(restore_setattr, "__mockrot_wrapper__", False):
            restore_setattr = _ORIGINAL_MONKEYPATCH_SETATTR
        if restore_setattr is not None:
            _mp.MonkeyPatch.setattr = restore_setattr  # type: ignore[assignment]
        _STATE.orig_monkeypatch_setattr = None

    _STATE.listener = None
    _STATE.is_installed = False
