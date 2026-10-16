"""Contract validation layer checking call signatures and return types."""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from typing import TYPE_CHECKING, Any, get_type_hints, is_typeddict

from pydantic import TypeAdapter, ValidationError

from mockrot.extractor import extract_contract
from mockrot.models import Contract, MockInteraction, Violation, ViolationKind

if TYPE_CHECKING:
    import inspect


def adjust_signature_for_call(
    sig: inspect.Signature,
    real_fn: Any,
    call_args: tuple[Any, ...],
) -> inspect.Signature:
    """Adjust signature when an implicit leading parameter (self/cls) is omitted by caller."""
    params = list(sig.parameters.values())
    if not params:
        return sig

    first_param = params[0].name
    if first_param not in ("self", "cls"):
        return sig

    # If real_fn is a top-level function (not defined inside a class), do not strip
    qualname = getattr(real_fn, "__qualname__", "")
    if "." not in qualname:
        return sig

    # Check if first arg could be the instance/class (unbound call Class.method(instance, ...))
    if len(call_args) > 0:
        first_arg = call_args[0]
        class_qualname = qualname.rsplit(".", 1)[0]
        class_name = class_qualname.split(".")[-1]
        if type(first_arg).__name__ == class_name or hasattr(
            first_arg, getattr(real_fn, "__name__", "")
        ):
            return sig

    # Otherwise, self/cls was omitted because mock was called as a bound method -> strip it
    return sig.replace(parameters=params[1:])


def _format_call_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Format call arguments for clear, actionable reporting."""
    parts: list[str] = []
    if args:
        parts.append(f"args={args!r}")
    if kwargs:
        parts.append(f"kwargs={kwargs!r}")
    return ", ".join(parts) if parts else "no arguments"


def _validate_dataclass_dict(cls: type[Any], data: dict[Any, Any]) -> None:
    """Validate a dictionary against dataclass field types in strict mode."""
    try:
        hints = get_type_hints(cls)
    except (NameError, TypeError):
        hints = getattr(cls, "__annotations__", {})
    for field in fields(cls):
        field_name = field.name
        if field_name not in data:
            if field.default is MISSING and field.default_factory is MISSING:
                raise ValueError(f"Missing required dataclass field '{field_name}'")
            continue
        field_type = hints.get(field_name, Any)
        TypeAdapter(field_type).validate_python(data[field_name], strict=True)


def _validate_typeddict(tp: type[Any], data: dict[Any, Any]) -> None:
    """Validate a dictionary against TypedDict field types in strict mode."""
    try:
        hints = get_type_hints(tp)
    except (NameError, TypeError):
        hints = getattr(tp, "__annotations__", {})
    required: frozenset[str] = getattr(tp, "__required_keys__", frozenset(hints.keys()))
    for key, field_type in hints.items():
        if key not in data:
            if key in required:
                raise ValueError(f"Missing required TypedDict key '{key}'")
            continue
        TypeAdapter(field_type).validate_python(data[key], strict=True)


def validate_signature(
    interaction: MockInteraction,
    contract: Contract,
) -> list[Violation]:
    """Validate that arguments passed to the mock match the real target signature."""
    if contract.signature is None:
        return []

    # If unittest.mock with autospec already raised TypeError, do not duplicate
    if isinstance(interaction.raised_exception, TypeError):
        exc_msg = str(interaction.raised_exception)
        if any(
            hint in exc_msg
            for hint in (
                "missing a required argument",
                "missing required argument",
                "unexpected keyword argument",
                "too many positional arguments",
                "got an unexpected keyword",
            )
        ):
            return []

    adjusted_sig = adjust_signature_for_call(
        contract.signature, interaction.target_func, interaction.args
    )

    try:
        adjusted_sig.bind(*interaction.args, **interaction.kwargs)
    except TypeError as exc:
        return [
            Violation(
                site=interaction.site,
                target_name=interaction.target_name,
                kind=ViolationKind.SIGNATURE_MISMATCH,
                message=str(exc),
                expected=f"Signature: {adjusted_sig}",
                actual=_format_call_args(interaction.args, interaction.kwargs),
            )
        ]

    return []


def validate_return_type(
    interaction: MockInteraction,
    contract: Contract,
) -> list[Violation]:
    """Validate that the value returned by the mock strictly satisfies the return type contract."""
    # Mocks raising an exception simulate error states; return type is not applicable
    if interaction.raised_exception is not None:
        return []

    ret_type = contract.return_type
    is_td = is_typeddict(ret_type)
    # If the contract has no return adapter and is not a TypedDict, nothing to validate
    if contract.return_adapter is None and not is_td:
        return []

    val: Any = interaction.returned_value
    val_obj: object = val

    # Exceptions (instances and classes) simulate error conditions and are always legitimate (F5)
    if isinstance(val, BaseException) or (isinstance(val, type) and issubclass(val, BaseException)):
        return []

    try:
        if is_td and isinstance(ret_type, type):
            if not isinstance(val, dict):
                type_name = getattr(ret_type, "__name__", str(ret_type))
                raise TypeError(
                    f"Expected dict for TypedDict {type_name}, got {type(val_obj).__name__}"
                )
            _validate_typeddict(ret_type, val)  # pyright: ignore[reportUnknownArgumentType] - pyright narrows Any to dict[Unknown, Unknown]
        elif (
            is_dataclass(contract.return_type)
            and isinstance(contract.return_type, type)
            and isinstance(val, dict)
        ):
            _validate_dataclass_dict(contract.return_type, val)  # pyright: ignore[reportUnknownArgumentType] - pyright narrows Any to dict[Unknown, Unknown]
        elif contract.return_adapter is not None:
            contract.return_adapter.validate_python(val, strict=True)
    except (ValidationError, TypeError, ValueError) as exc:
        expected_desc = getattr(contract.return_type, "__name__", str(contract.return_type))
        actual_desc = f"{type(val_obj).__name__}: {val_obj!r}"
        return [
            Violation(
                site=interaction.site,
                target_name=interaction.target_name,
                kind=ViolationKind.RETURN_TYPE_DRIFT,
                message=str(exc),
                expected=expected_desc,
                actual=actual_desc,
            )
        ]

    return []


def validate_async(
    interaction: MockInteraction,
    contract: Contract,
) -> list[Violation]:
    """Validate that synchronous and asynchronous invocation conventions match target contract."""
    # 1. Target is an async coroutine function, but interaction was synchronous
    if contract.is_async and not interaction.is_async_call:
        actual_desc = (
            f"Synchronous call returning {type(interaction.returned_value).__name__}"
            if interaction.raised_exception is None
            else f"Synchronous call raising {type(interaction.raised_exception).__name__}"
        )
        return [
            Violation(
                site=interaction.site,
                target_name=interaction.target_name,
                kind=ViolationKind.ASYNC_MISMATCH,
                message=(
                    f"Target '{contract.target_name}' is an async coroutine function "
                    "('async def'), but was mocked or invoked synchronously."
                ),
                expected="async def / coroutine function (awaited)",
                actual=actual_desc,
            )
        ]

    # 2. Target is a synchronous function, but interaction was asynchronous
    if not contract.is_async and interaction.is_async_call:
        return [
            Violation(
                site=interaction.site,
                target_name=interaction.target_name,
                kind=ViolationKind.ASYNC_MISMATCH,
                message=(
                    f"Target '{contract.target_name}' is a synchronous function, "
                    "but was mocked with an AsyncMock or invoked asynchronously."
                ),
                expected="Synchronous function (not awaited)",
                actual="AsyncMock / coroutine (awaited)",
            )
        ]

    return []


def validate_interaction(interaction: MockInteraction) -> list[Violation]:
    """Validate a mock call interaction against the target function contract."""
    if interaction.target_func is None:
        return []

    contract = extract_contract(interaction.target_func)
    violations: list[Violation] = []

    # 1. Async calling convention validation (F4)
    violations.extend(validate_async(interaction, contract))

    # 2. Signature validation (F2)
    violations.extend(validate_signature(interaction, contract))

    # 3. Strict return type validation (F3)
    violations.extend(validate_return_type(interaction, contract))

    return violations
