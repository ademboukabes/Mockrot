"""Unit tests for contract signature validation (F2)."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import TypedDict

from pydantic import BaseModel

import mockrot.validator
from mockrot.extractor import extract_contract
from mockrot.models import Contract, MockInteraction, MockSite, ViolationKind
from mockrot.validator import (
    adjust_signature_for_call,
    validate_async,
    validate_interaction,
    validate_signature,
)

importlib.reload(mockrot.validator)


class UserService:
    """Sample class for method signature validation."""

    def get_user(self, user_id: int, include_roles: bool = False) -> str:
        return f"{user_id}:{include_roles}"

    def delete_user(self) -> None:
        pass


def top_level_with_self(self: str, val: int) -> str:
    """Top level function having a parameter named self."""
    return f"{self}:{val}"


def sample_api_call(query: str, *, timeout: int) -> dict[str, str]:
    """Function with keyword-only argument."""
    return {"query": query, "timeout": str(timeout)}


def simple_target(a: int, b: str = "default") -> None:
    pass


def make_site() -> MockSite:
    return MockSite(file_path="tests/test_demo.py", line_number=42, test_name="test_foo")


def test_adjust_signature_for_bound_instance_call() -> None:
    sig = inspect.signature(UserService.get_user)
    # Call without self (bound call: user_id=123)
    adjusted = adjust_signature_for_call(sig, UserService.get_user, (123,))
    assert "self" not in adjusted.parameters
    assert list(adjusted.parameters.keys()) == ["user_id", "include_roles"]


def test_adjust_signature_for_unbound_call_with_instance() -> None:
    sig = inspect.signature(UserService.get_user)
    service = UserService()
    # Call with self passed explicitly: (service, 123)
    adjusted = adjust_signature_for_call(sig, UserService.get_user, (service, 123))
    assert "self" in adjusted.parameters
    assert list(adjusted.parameters.keys()) == ["self", "user_id", "include_roles"]


def test_adjust_signature_for_top_level_function_keeps_self() -> None:
    sig = inspect.signature(top_level_with_self)
    adjusted = adjust_signature_for_call(sig, top_level_with_self, ("abc", 1))
    assert "self" in adjusted.parameters


def test_validate_signature_detects_missing_required_positional_arg() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="tests.simple_target",
        args=(),  # missing 'a'
        kwargs={},
        returned_value=None,
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == ViolationKind.SIGNATURE_MISMATCH
    assert "missing a required argument" in v.message
    assert "a" in v.message
    assert "tests.simple_target" in v.target_name


def test_validate_signature_detects_missing_keyword_only_arg() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=sample_api_call,
        target_name="tests.sample_api_call",
        args=("search",),
        kwargs={},  # missing required keyword-only 'timeout'
        returned_value={"query": "search", "timeout": "10"},
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == ViolationKind.SIGNATURE_MISMATCH
    assert "timeout" in v.message


def test_validate_signature_detects_unexpected_keyword_argument() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="tests.simple_target",
        args=(1,),
        kwargs={"removed_param": True},
        returned_value=None,
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == ViolationKind.SIGNATURE_MISMATCH
    assert "unexpected keyword argument 'removed_param'" in v.message


def test_validate_signature_detects_too_many_positional_arguments() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="tests.simple_target",
        args=(1, "custom", 999),  # 3 args, max is 2
        kwargs={},
        returned_value=None,
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == ViolationKind.SIGNATURE_MISMATCH
    assert "too many positional arguments" in v.message


def test_validate_signature_valid_calls_produce_zero_violations() -> None:
    # 1. Positional call
    v1 = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=simple_target,
            target_name="tests.simple_target",
            args=(10,),
            kwargs={},
        )
    )
    assert v1 == []

    # 2. Keyword call
    v2 = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=simple_target,
            target_name="tests.simple_target",
            args=(),
            kwargs={"a": 10, "b": "hello"},
        )
    )
    assert v2 == []

    # 3. Method call on instance (bound call without self)
    v3 = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=UserService.get_user,
            target_name="tests.UserService.get_user",
            args=(42,),
            kwargs={"include_roles": True},
            returned_value="42:True",
        )
    )
    assert v3 == []


def test_validate_signature_skips_when_mock_already_raised_type_error() -> None:
    # If unittest.mock with autospec=True already raised TypeError from binding
    simulated_autospec_exc = TypeError("missing a required argument: 'a'")
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="tests.simple_target",
        args=(),
        kwargs={},
        raised_exception=simulated_autospec_exc,
    )
    violations = validate_interaction(interaction)
    # Should not produce duplicate violation since unittest.mock already caught it
    assert violations == []


def test_validate_signature_handles_none_or_no_signature() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=None,
        target_name="unknown",
        args=(1, 2),
        kwargs={},
    )
    assert validate_interaction(interaction) == []


def test_validate_signature_direct_call_with_contract() -> None:
    contract = Contract(
        target_name="dummy",
        is_async=False,
        has_return_annotation=False,
        signature=inspect.signature(simple_target),
    )
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="dummy",
        args=(1, "custom"),
        kwargs={},
    )
    assert validate_signature(interaction, contract) == []


def test_adjust_signature_empty_parameters() -> None:
    def no_param_func() -> None:
        pass

    sig = inspect.signature(no_param_func)
    adjusted = adjust_signature_for_call(sig, no_param_func, ())
    assert len(adjusted.parameters) == 0


def test_adjust_signature_method_called_with_empty_args() -> None:
    sig = inspect.signature(UserService.delete_user)
    # Called on instance without args: notifier.delete_user()
    adjusted = adjust_signature_for_call(sig, UserService.delete_user, ())
    assert "self" not in adjusted.parameters
    assert len(adjusted.parameters) == 0


def test_validate_signature_with_unrelated_type_error_still_validates() -> None:
    # A TypeError raised by internal app logic, not unittest.mock argument binding
    app_exception = TypeError("unsupported operand type(s) for +: 'int' and 'str'")
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="tests.simple_target",
        args=(1,),
        kwargs={"bad_kwarg": 123},
        raised_exception=app_exception,
    )
    violations = validate_interaction(interaction)
    # Should still detect the invalid parameter bad_kwarg
    assert len(violations) == 1
    assert "unexpected keyword argument 'bad_kwarg'" in violations[0].message


def test_validate_signature_reports_no_arguments_when_both_empty() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="tests.simple_target",
        args=(),
        kwargs={},
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    assert violations[0].actual == "no arguments"


def test_validate_signature_with_none_signature_in_contract() -> None:
    contract = Contract(
        target_name="dummy",
        is_async=False,
        has_return_annotation=False,
        signature=None,
    )
    interaction = MockInteraction(
        site=make_site(),
        target_func=simple_target,
        target_name="dummy",
        args=(),
        kwargs={},
    )
    assert validate_signature(interaction, contract) == []


# --- Return type validation tests (F3) ---


class SampleUserModel(BaseModel):
    id: int
    name: str


@dataclass
class SamplePoint:
    x: int
    y: int


class SampleConfig(TypedDict):
    timeout: float
    retries: int


def returns_int(x: int) -> int:
    return x


def returns_user() -> SampleUserModel:
    return SampleUserModel(id=1, name="alice")


def returns_point() -> SamplePoint:
    return SamplePoint(1, 2)


def returns_config() -> SampleConfig:
    return {"timeout": 1.5, "retries": 3}


def returns_optional(flag: bool) -> int | None:
    return 10 if flag else None


def test_validate_return_type_strict_scalar_mismatch() -> None:
    # Function returns int, mock returns string "5000"
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_int,
        target_name="tests.returns_int",
        args=(1,),
        kwargs={},
        returned_value="5000",
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == ViolationKind.RETURN_TYPE_DRIFT
    assert "int" in v.expected.lower()
    assert "str: '5000'" in v.actual


def test_validate_return_type_strict_scalar_valid() -> None:
    # Function returns int, mock returns int 5000
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_int,
        target_name="tests.returns_int",
        args=(1,),
        kwargs={},
        returned_value=5000,
    )
    assert validate_interaction(interaction) == []


def test_validate_return_type_pydantic_model_mismatch() -> None:
    # Pydantic model requires int id, mock passes string id
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_user,
        target_name="tests.returns_user",
        args=(),
        kwargs={},
        returned_value={"id": "5000", "name": "alice"},
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.RETURN_TYPE_DRIFT


def test_validate_return_type_pydantic_model_valid() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_user,
        target_name="tests.returns_user",
        args=(),
        kwargs={},
        returned_value={"id": 5000, "name": "alice"},
    )
    assert validate_interaction(interaction) == []


def test_validate_return_type_dataclass_dict() -> None:
    # 1. Valid dict
    v_ok = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=returns_point,
            target_name="tests.returns_point",
            args=(),
            kwargs={},
            returned_value={"x": 10, "y": 20},
        )
    )
    assert v_ok == []

    # 2. Type mismatch inside dict
    v_bad = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=returns_point,
            target_name="tests.returns_point",
            args=(),
            kwargs={},
            returned_value={"x": "10", "y": 20},
        )
    )
    assert len(v_bad) == 1
    assert v_bad[0].kind == ViolationKind.RETURN_TYPE_DRIFT


def test_validate_return_type_typeddict() -> None:
    # 1. Valid dict
    v_ok = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=returns_config,
            target_name="tests.returns_config",
            args=(),
            kwargs={},
            returned_value={"timeout": 5.0, "retries": 3},
        )
    )
    assert v_ok == []

    # 2. Invalid field type
    v_bad = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=returns_config,
            target_name="tests.returns_config",
            args=(),
            kwargs={},
            returned_value={"timeout": "5.0", "retries": 3},
        )
    )
    assert len(v_bad) == 1
    assert v_bad[0].kind == ViolationKind.RETURN_TYPE_DRIFT


def test_validate_return_type_optional_and_union() -> None:
    # Valid None
    assert (
        validate_interaction(
            MockInteraction(
                site=make_site(),
                target_func=returns_optional,
                target_name="tests.returns_optional",
                args=(False,),
                kwargs={},
                returned_value=None,
            )
        )
        == []
    )

    # Valid int
    assert (
        validate_interaction(
            MockInteraction(
                site=make_site(),
                target_func=returns_optional,
                target_name="tests.returns_optional",
                args=(True,),
                kwargs={},
                returned_value=42,
            )
        )
        == []
    )

    # Invalid str
    v = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=returns_optional,
            target_name="tests.returns_optional",
            args=(True,),
            kwargs={},
            returned_value="42",
        )
    )
    assert len(v) == 1
    assert v[0].kind == ViolationKind.RETURN_TYPE_DRIFT


def test_validate_return_type_ignores_simulated_exceptions() -> None:
    # side_effect = TimeoutError(...) should not trigger return type violation
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_int,
        target_name="tests.returns_int",
        args=(1,),
        kwargs={},
        returned_value=None,
        raised_exception=TimeoutError("gateway timeout"),
    )
    assert validate_interaction(interaction) == []


def test_validate_return_type_dataclass_missing_required_field() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_point,
        target_name="tests.returns_point",
        args=(),
        kwargs={},
        returned_value={"x": 10},  # missing required 'y'
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    assert "Missing required dataclass field 'y'" in violations[0].message


async def async_fetch_user(user_id: int) -> SampleUserModel:
    return SampleUserModel(id=user_id, name="alice")


async def async_calc(x: int, y: int = 10) -> int:
    return x + y


def test_validate_async_detects_sync_call_on_async_target() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=async_fetch_user,
        target_name="tests.async_fetch_user",
        args=(1,),
        kwargs={},
        returned_value={"id": 1, "name": "alice"},
        is_async_call=False,
    )
    contract = extract_contract(async_fetch_user)
    direct_violations = validate_async(interaction, contract)
    assert len(direct_violations) == 1
    assert direct_violations[0].kind == ViolationKind.ASYNC_MISMATCH

    violations = validate_interaction(interaction)
    assert any(v.kind == ViolationKind.ASYNC_MISMATCH for v in violations)
    v_async = next(v for v in violations if v.kind == ViolationKind.ASYNC_MISMATCH)
    assert "async def" in v_async.message
    assert "Synchronous call" in v_async.actual


def test_validate_async_detects_async_call_on_sync_target() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_int,
        target_name="tests.returns_int",
        args=(1,),
        kwargs={},
        returned_value=1,
        is_async_call=True,
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.ASYNC_MISMATCH
    assert "synchronous function" in violations[0].message


def test_validate_async_valid_call_passes() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=async_calc,
        target_name="tests.async_calc",
        args=(5,),
        kwargs={"y": 20},
        returned_value=25,
        is_async_call=True,
    )
    assert validate_interaction(interaction) == []


def test_validate_async_valid_pydantic_return_passes() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=async_fetch_user,
        target_name="tests.async_fetch_user",
        args=(42,),
        kwargs={},
        returned_value={"id": 42, "name": "bob"},
        is_async_call=True,
    )
    assert validate_interaction(interaction) == []


def test_validate_async_detects_return_type_drift_after_await() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=async_calc,
        target_name="tests.async_calc",
        args=(5,),
        kwargs={},
        returned_value="25",  # string instead of int
        is_async_call=True,
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.RETURN_TYPE_DRIFT


def test_validate_async_detects_signature_mismatch_on_async_call() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=async_calc,
        target_name="tests.async_calc",
        args=(),  # missing required positional arg 'x'
        kwargs={},
        returned_value=10,
        is_async_call=True,
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.SIGNATURE_MISMATCH


def test_validate_async_ignores_simulated_exception_on_async_call() -> None:
    interaction = MockInteraction(
        site=make_site(),
        target_func=async_calc,
        target_name="tests.async_calc",
        args=(5,),
        kwargs={},
        raised_exception=ConnectionResetError("lost connection"),
        is_async_call=True,
    )
    assert validate_interaction(interaction) == []


def test_side_effect_iterable_all_valid() -> None:
    values = [10, 20, 30]
    for val in values:
        interaction = MockInteraction(
            site=make_site(),
            target_func=returns_int,
            target_name="tests.returns_int",
            args=(val,),
            kwargs={},
            returned_value=val,
        )
        assert validate_interaction(interaction) == []


def test_side_effect_iterable_detects_drift_on_specific_call() -> None:
    calls = [100, "string_is_invalid", 300]
    results = [
        validate_interaction(
            MockInteraction(
                site=make_site(),
                target_func=returns_int,
                target_name="tests.returns_int",
                args=(1,),
                kwargs={},
                returned_value=c,
            )
        )
        for c in calls
    ]
    # First call valid
    assert results[0] == []
    # Second call detects drift
    assert len(results[1]) == 1
    assert results[1][0].kind == ViolationKind.RETURN_TYPE_DRIFT
    # Third call valid
    assert results[2] == []


def test_side_effect_iterable_mixed_with_raised_exceptions() -> None:
    # 1. Normal return
    v1 = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=returns_int,
            target_name="tests.returns_int",
            args=(1,),
            kwargs={},
            returned_value=10,
        )
    )
    assert v1 == []

    # 2. Raised exception (e.g. mock.side_effect = [10, TimeoutError("timed out")])
    v2 = validate_interaction(
        MockInteraction(
            site=make_site(),
            target_func=returns_int,
            target_name="tests.returns_int",
            args=(1,),
            kwargs={},
            returned_value=None,
            raised_exception=TimeoutError("timed out"),
        )
    )
    assert v2 == []


def test_side_effect_callable_returning_exception_instance_is_immune() -> None:
    # When a custom side_effect callable returns an Exception instance to simulate error
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_int,
        target_name="tests.returns_int",
        args=(1,),
        kwargs={},
        returned_value=ValueError("simulated error value"),
    )
    assert validate_interaction(interaction) == []


def test_side_effect_callable_returning_exception_class_is_immune() -> None:
    # When a custom side_effect callable returns an Exception class
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_int,
        target_name="tests.returns_int",
        args=(1,),
        kwargs={},
        returned_value=KeyError,
    )
    assert validate_interaction(interaction) == []


def test_side_effect_callable_returning_invalid_scalar_triggers_drift() -> None:
    # Custom side_effect callable returning invalid type
    interaction = MockInteraction(
        site=make_site(),
        target_func=returns_int,
        target_name="tests.returns_int",
        args=(5,),
        kwargs={},
        returned_value="bad_return",
    )
    violations = validate_interaction(interaction)
    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.RETURN_TYPE_DRIFT
