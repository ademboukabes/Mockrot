"""Integration tests verifying end-to-end zombie field detection (F6) with pytester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_zombie_fields_warn_mode_reports_summary(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        accounts="""
        from pydantic import BaseModel

        class Account(BaseModel):
            account_id: int
            holder_name: str

        def get_account(acc_id: int) -> Account:
            return Account(account_id=acc_id, holder_name="Acme Corp")
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import accounts

        @patch("accounts.get_account", return_value={
            "account_id": 100,
            "holder_name": "Acme Corp",
            "old_routing_number": "123456789",  # Zombie field
        })
        def test_account_with_zombie_key(mock_acc):
            acc = accounts.get_account(100)
            assert acc["account_id"] == 100
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*= Mockrot: Rotting Mocks Detected =*",
            "*[zombie_field]*accounts.get_account*",
            "*Zombie field 'old_routing_number' detected in mocked dictionary for Account*",
            "*1 rotting mock(s) detected*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_zombie_fields_strict_mode_fails_test(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        accounts="""
        from pydantic import BaseModel

        class Account(BaseModel):
            account_id: int
            holder_name: str

        def get_account(acc_id: int) -> Account:
            return Account(account_id=acc_id, holder_name="Acme Corp")
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import accounts

        @patch("accounts.get_account", return_value={
            "account_id": 100,
            "holder_name": "Acme Corp",
            "old_routing_number": "123456789",  # Zombie field
        })
        def test_account_with_zombie_key_strict(mock_acc):
            accounts.get_account(100)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (zombie_field):*",
            "*Target:*accounts.get_account*",
            "*Zombie field 'old_routing_number' detected in mocked dictionary for Account*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1


def test_nested_zombie_fields_detected_in_strict(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        profiles="""
        from pydantic import BaseModel

        class Address(BaseModel):
            city: str
            zip_code: str

        class Profile(BaseModel):
            user_id: int
            address: Address

        def get_profile(user_id: int) -> Profile:
            return Profile(user_id=user_id, address=Address(city="Paris", zip_code="75001"))
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import profiles

        @patch("profiles.get_profile", return_value={
            "user_id": 1,
            "address": {
                "city": "Paris",
                "zip_code": "75001",
                "building_code": "A4",  # Nested zombie field
            },
        })
        def test_nested_zombie_field_strict(mock_p):
            profiles.get_profile(1)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*Mockrot detected rotting mock (zombie_field):*",
            "*Target:*profiles.get_profile*",
            "*Zombie field 'address.building_code' detected in mocked dictionary for Address*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1


def test_valid_mocked_dict_passes_in_strict(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        accounts="""
        from pydantic import BaseModel

        class Account(BaseModel):
            account_id: int
            holder_name: str

        def get_account(acc_id: int) -> Account:
            return Account(account_id=acc_id, holder_name="Acme Corp")
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import accounts

        @patch("accounts.get_account", return_value={
            "account_id": 100,
            "holder_name": "Acme Corp",
        })
        def test_account_valid(mock_acc):
            acc = accounts.get_account(100)
            assert acc["account_id"] == 100
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_typeddict_zombie_field_detected_in_strict(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        settings="""
        from typing import TypedDict

        class AppConfig(TypedDict):
            host: str
            port: int

        def load_config() -> AppConfig:
            return {"host": "localhost", "port": 8080}
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import settings

        @patch("settings.load_config", return_value={
            "host": "localhost",
            "port": 8080,
            "deprecated_debug_flag": True,  # Zombie key in TypedDict
        })
        def test_typeddict_zombie(mock_cfg):
            settings.load_config()
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*Mockrot detected rotting mock (zombie_field):*",
            "*Target:*settings.load_config*",
            "*Zombie field 'deprecated_debug_flag' detected in mocked dictionary for AppConfig*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1
