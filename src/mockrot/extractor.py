"""Contract extraction layer inspecting signatures and type metadata."""

from __future__ import annotations

import inspect
import sys
import weakref
from typing import Any, get_type_hints

from pydantic import TypeAdapter
from pydantic.errors import PydanticUserError

from mockrot.models import Contract

# Two-tier cache: WeakKeyDictionary for living objects (zero memory leak),
# mapping underlying callable -> dict[is_bound, Contract].
# Fallback to static key (module, qualname, is_bound) for unhashable or non-weakrefable callables.
_CONTRACT_CACHE: weakref.WeakKeyDictionary[Any, dict[bool, Contract]] = weakref.WeakKeyDictionary()
_STATIC_CONTRACT_CACHE: dict[tuple[str, str, bool], Contract] = {}


def clear_extractor_cache() -> None:
    """Clear all cached contracts (primarily used for test isolation)."""
    _CONTRACT_CACHE.clear()
    _STATIC_CONTRACT_CACHE.clear()


def _get_target_qualname(target: Any) -> str:
    """Build a reliable identifier from target module and qualname."""
    module = getattr(target, "__module__", "")
    qualname = getattr(target, "__qualname__", getattr(target, "__name__", str(target)))
    return f"{module}.{qualname}" if module else qualname


def _resolve_type_hints_return(real_fn: Any, globalns: dict[str, Any] | None) -> Any | None:
    """Attempt resolving return annotation using typing.get_type_hints."""
    try:
        hints = get_type_hints(real_fn, globalns=globalns)
        ret = hints.get("return")
        if ret is not None and ret is not type(None):
            return ret
    except NameError:
        # Resolve closure or local function annotations by inspecting caller frames
        try:
            merged_locals: dict[str, Any] = {}
            frame = inspect.currentframe()
            while frame:
                merged_locals.update(frame.f_locals)
                frame = frame.f_back
            hints = get_type_hints(real_fn, globalns=globalns, localns=merged_locals)
            ret = hints.get("return")
            if ret is not None and ret is not type(None):
                return ret
        except (NameError, TypeError, ValueError):
            return None
    except (TypeError, ValueError, AttributeError):
        return None
    return None


def _resolve_raw_annotations_return(
    real_fn: Any, underlying: Any, globalns: dict[str, Any] | None
) -> Any | None:
    """Fallback resolving return type from raw annotations or string evaluation."""
    annotations: dict[str, Any] = getattr(real_fn, "__annotations__", {}) or getattr(
        underlying, "__annotations__", {}
    )
    raw_ret = annotations.get("return")
    if raw_ret is None or raw_ret is type(None) or raw_ret == "None":
        return None

    if isinstance(raw_ret, str):
        try:
            resolved = eval(raw_ret, globalns)
            if resolved is not None and resolved is not type(None):
                return resolved
        except (NameError, TypeError, ValueError, SyntaxError):
            return None
        return None

    return raw_ret


def _resolve_return_type(
    real_fn: Any, underlying: Any
) -> tuple[Any | None, TypeAdapter[Any] | None]:
    """Resolve return type annotation and compile its Pydantic TypeAdapter."""
    mod_name = getattr(underlying, "__module__", "")
    mod = sys.modules.get(mod_name)
    globalns = getattr(mod, "__dict__", None)

    ret = _resolve_type_hints_return(real_fn, globalns)
    if ret is None and underlying is not real_fn:
        ret = _resolve_type_hints_return(underlying, globalns)
    if ret is None:
        ret = _resolve_raw_annotations_return(real_fn, underlying, globalns)

    adapter: TypeAdapter[Any] | None = None
    if ret is not None:
        try:
            adapter = TypeAdapter(ret)
        except (PydanticUserError, TypeError, ValueError):
            adapter = None

    return ret, adapter


def extract_contract(real_fn: Any) -> Contract:
    """Extract runtime contract (signature, async status, annotations) from a callable.

    Features two-tier caching to prevent memory leaks and protect against Python
    id() recycling or non-hashable callables. Distinguishes bound and unbound callables.
    """
    if real_fn is None:
        return Contract(
            target_name="unknown",
            is_async=False,
            has_return_annotation=False,
            signature=None,
            return_type=None,
            return_adapter=None,
        )

    underlying = getattr(real_fn, "__func__", real_fn)
    is_bound = hasattr(real_fn, "__self__") and real_fn.__self__ is not None

    # 1. Check caches
    try:
        if is_bound in _CONTRACT_CACHE[underlying]:
            return _CONTRACT_CACHE[underlying][is_bound]
    except (KeyError, TypeError):
        key = (
            getattr(underlying, "__module__", ""),
            getattr(underlying, "__qualname__", getattr(underlying, "__name__", "")),
            is_bound,
        )
        if key in _STATIC_CONTRACT_CACHE:
            return _STATIC_CONTRACT_CACHE[key]

    # 2. Extract signature with graceful fallback for C builtins or unsupported callables
    try:
        sig = inspect.signature(real_fn)
    except (ValueError, TypeError):
        sig = None

    # 3. Determine if coroutine function
    is_async = inspect.iscoroutinefunction(real_fn) or inspect.iscoroutinefunction(underlying)

    # 4. Extract return type annotation and compile TypeAdapter
    return_type, return_adapter = _resolve_return_type(real_fn, underlying)
    has_return = return_type is not None or (
        sig is not None
        and sig.return_annotation is not inspect.Signature.empty
        and sig.return_annotation is not None
    )

    target_name = _get_target_qualname(real_fn)
    contract = Contract(
        target_name=target_name,
        is_async=is_async,
        has_return_annotation=has_return,
        signature=sig,
        return_type=return_type,
        return_adapter=return_adapter,
    )

    # 5. Populate cache
    try:
        if underlying not in _CONTRACT_CACHE:
            _CONTRACT_CACHE[underlying] = {}
        _CONTRACT_CACHE[underlying][is_bound] = contract
    except TypeError:
        key = (
            getattr(underlying, "__module__", ""),
            getattr(underlying, "__qualname__", getattr(underlying, "__name__", "")),
            is_bound,
        )
        _STATIC_CONTRACT_CACHE[key] = contract

    return contract
