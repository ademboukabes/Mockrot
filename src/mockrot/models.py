"""Domain models for Mockrot contracts, violations, and call sites."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import inspect


class ViolationKind(str, Enum):
    """Enumeration of violation types detected on mocked targets."""

    SIGNATURE_MISMATCH = "signature_mismatch"
    RETURN_TYPE_DRIFT = "return_type_drift"
    ASYNC_MISMATCH = "async_mismatch"
    ZOMBIE_FIELD = "zombie_field"


@dataclass(frozen=True, slots=True)
class MockSite:
    """Location where a mock was instantiated or interacted with."""

    file_path: str
    line_number: int
    test_name: str = ""


@dataclass(frozen=True, slots=True)
class Violation:
    """Details of a single contract drift detected on a mock."""

    site: MockSite
    target_name: str
    kind: ViolationKind
    message: str
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True, slots=True)
class Contract:
    """Extracted runtime contract for a target function or method."""

    target_name: str
    is_async: bool
    has_return_annotation: bool
    signature: inspect.Signature | None = None
    return_type: Any | None = None
    return_adapter: Any | None = None


@dataclass(frozen=True, slots=True)
class MockInteraction:
    """Details of a single call interaction intercepted on a mock."""

    site: MockSite
    target_func: Any
    target_name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    returned_value: Any = None
    raised_exception: BaseException | None = None
    is_async_call: bool = False
