"""Unit tests for contract signature validation (F2)."""

from __future__ import annotations

import importlib
import inspect

import mockrot.validator
from mockrot.models import Contract, MockInteraction, MockSite, ViolationKind
from mockrot.validator import (
    adjust_signature_for_call,
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
        returned_value=None,
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
