"""Contract extraction layer inspecting signatures and type metadata."""

from __future__ import annotations

import inspect
import weakref
from typing import Any

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

    # 4. Check for return annotation presence
    has_return = (
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
