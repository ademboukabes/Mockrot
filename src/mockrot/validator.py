"""Contract validation layer checking call signatures and return types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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


def validate_interaction(interaction: MockInteraction) -> list[Violation]:
    """Validate a mock call interaction against the target function contract."""
    if interaction.target_func is None:
        return []

    contract = extract_contract(interaction.target_func)
    violations: list[Violation] = []

    # 1. Signature validation (F2)
    violations.extend(validate_signature(interaction, contract))

    return violations
