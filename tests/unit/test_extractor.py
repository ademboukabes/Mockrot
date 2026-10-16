"""Unit tests for contract extraction and signature inspection (F2)."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from mockrot.extractor import clear_extractor_cache, extract_contract


def sample_sync_func(user_id: int, flag: bool = False) -> str:
    """Sample sync function with full type annotations."""
    return f"{user_id}:{flag}"


async def sample_async_func(query: str, limit: int = 10) -> list[str]:
    """Sample async function."""
    return [query] * limit


def untyped_func(a: int, b: int = 0):  # pyright: ignore[reportUnknownParameterType]
    """Function without return type annotation."""
    return a + b


class Calculator:
    """Sample class for method contract tests."""

    def add(self, a: int, b: int) -> int:
        return a + b

    @classmethod
    def create(cls, seed: int) -> Calculator:
        del seed
        return cls()

    @staticmethod
    def ping() -> bool:
        return True


def test_extract_contract_for_standard_function() -> None:
    clear_extractor_cache()
    contract = extract_contract(sample_sync_func)

    assert contract.target_name.endswith("sample_sync_func")
    assert contract.is_async is False
    assert contract.has_return_annotation is True
    assert contract.signature is not None
    assert contract.return_type is str
    assert contract.return_adapter is not None

    params = list(contract.signature.parameters.keys())
    assert params == ["user_id", "flag"]


def test_extract_contract_for_async_function() -> None:
    clear_extractor_cache()
    contract = extract_contract(sample_async_func)

    assert contract.is_async is True
    assert contract.has_return_annotation is True
    assert contract.signature is not None
    assert contract.return_type == list[str]
    assert contract.return_adapter is not None
    assert list(contract.signature.parameters.keys()) == ["query", "limit"]


def test_extract_contract_without_return_annotation() -> None:
    clear_extractor_cache()
    contract = extract_contract(untyped_func)

    assert contract.has_return_annotation is False
    assert contract.signature is not None
    assert contract.return_type is None
    assert contract.return_adapter is None
    assert list(contract.signature.parameters.keys()) == ["a", "b"]


def test_extract_contract_for_class_methods() -> None:
    clear_extractor_cache()
    inst = Calculator()

    contract_bound = extract_contract(inst.add)
    assert contract_bound.signature is not None
    assert "self" not in contract_bound.signature.parameters

    contract_unbound = extract_contract(Calculator.add)
    assert contract_unbound.signature is not None
    assert "self" in contract_unbound.signature.parameters

    contract_classmethod = extract_contract(Calculator.create)
    assert contract_classmethod.signature is not None

    contract_static = extract_contract(Calculator.ping)
    assert contract_static.signature is not None


def test_extract_contract_two_tier_caching() -> None:
    clear_extractor_cache()

    contract1 = extract_contract(sample_sync_func)
    contract2 = extract_contract(sample_sync_func)
    assert contract1 is contract2

    # Test static fallback cache with a callable whose weakref fails
    class UnweakrefableCallable:
        __slots__ = ("__name__", "__qualname__")

        def __init__(self) -> None:
            self.__name__ = "dummy"
            self.__qualname__ = "dummy"

        def __call__(self, x: int) -> int:
            return x

    target = UnweakrefableCallable()
    contract_static1 = extract_contract(target)
    contract_static2 = extract_contract(target)
    assert contract_static1 == contract_static2


def test_extract_contract_handles_builtins_without_signature() -> None:
    clear_extractor_cache()

    # int and object have signatures, but builtins or custom slot methods can raise ValueError
    # We can pass an object whose signature raises ValueError to test graceful degradation
    class NoSigCallable:
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            pass

    no_sig = NoSigCallable()
    # monkeypatch inspect.signature for this specific instance to simulate C native
    # without a discoverable signature.
    orig_sig = inspect.signature

    def mock_sig(obj: Any, **kwargs: Any) -> Any:
        if obj is no_sig:
            raise ValueError("no signature found")
        return orig_sig(obj, **kwargs)

    inspect.signature = mock_sig  # type: ignore[assignment]
    try:
        contract = extract_contract(no_sig)
        assert contract.signature is None
    finally:
        inspect.signature = orig_sig  # type: ignore[assignment]


def test_extract_contract_handles_none_or_non_callable() -> None:
    clear_extractor_cache()
    contract = extract_contract(None)
    assert contract.signature is None
    assert contract.target_name == "unknown"
    assert contract.return_type is None
    assert contract.return_adapter is None


def test_extract_contract_for_pydantic_model_return() -> None:
    class UserDTO(BaseModel):
        id: int
        name: str

    def get_user() -> UserDTO:
        return UserDTO(id=1, name="alice")

    clear_extractor_cache()
    contract = extract_contract(get_user)
    assert contract.return_type is UserDTO
    assert contract.return_adapter is not None


def test_extract_contract_for_void_function_has_no_adapter() -> None:
    def void_func() -> None:
        pass

    clear_extractor_cache()
    contract = extract_contract(void_func)
    # Void function: return_type is None, adapter is None
    assert contract.return_type is None
    assert contract.return_adapter is None


class GlobalPayload(BaseModel):
    token: str


def func_with_string_annotation() -> GlobalPayload:
    return GlobalPayload(token="tok")


def test_extract_contract_resolves_string_annotation_via_globals() -> None:
    clear_extractor_cache()
    contract = extract_contract(func_with_string_annotation)
    assert contract.return_type is GlobalPayload
    assert contract.return_adapter is not None
