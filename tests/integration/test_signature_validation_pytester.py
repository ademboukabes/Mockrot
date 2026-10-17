"""Integration tests verifying end-to-end call signature validation (F2) with pytester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_signature_drift_warn_mode_passes_and_reports_summary(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def compute_tax(amount: int, rate: float) -> float:
            return amount * rate
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import app

        @patch("app.compute_tax", return_value=15.0)
        def test_compute_tax_drift(mock_tax):
            # Signature expects (amount, rate), caller provides only 1 argument
            res = app.compute_tax(100)
            assert res == 15.0
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*= Mockrot: Rotting Mocks Detected =*",
            "*[signature_mismatch]*compute_tax*",
            "*Expected: Signature: (amount: int, rate: float)*",
            "*missing a required argument*rate*",
            "*1 rotting mock(s) detected*",
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_signature_drift_strict_mode_fails_test(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def fetch_user(user_id: int, include_roles: bool = False) -> dict:
            return {"id": user_id, "roles": []}
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import app

        @patch("app.fetch_user", return_value={"id": 1})
        def test_fetch_user_obsolete_param(mock_fetch):
            # Caller passes removed argument 'tenant_id'
            app.fetch_user(1, tenant_id="tenant_123")
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=strict)*",
            "*Mockrot detected rotting mock (signature_mismatch):*",
            "*Target:*fetch_user*",
            "*Error:*got an unexpected keyword argument 'tenant_id'*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1


def test_signature_drift_exempt_via_marker(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def process(data: str) -> None:
            pass
        """
    )
    pytester.makepyfile("""
        import pytest
        from unittest.mock import patch
        import app

        @pytest.mark.mockrot_ignore
        @patch("app.process")
        def test_deliberate_bad_call(mock_proc):
            # Intentionally call with wrong signature
            app.process(bad_arg=42)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_valid_call_passes_in_strict_mode(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        app="""
        def add_items(a: int, b: int = 0) -> int:
            return a + b
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        import app

        @patch("app.add_items", return_value=42)
        def test_valid_signature_call(mock_add):
            val = app.add_items(10, b=32)
            assert val == 42
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_signature_drift_on_class_method(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        services="""
        class Notifier:
            def send(self, recipient: str, body: str) -> bool:
                return True
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        from services import Notifier

        @patch.object(Notifier, "send", return_value=True)
        def test_method_signature_drift(mock_send):
            notifier = Notifier()
            # Missing required 'body' argument
            notifier.send("alice@example.com")
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*Mockrot detected rotting mock (signature_mismatch):*",
            "*missing a required argument*body*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1


def test_signature_drift_on_async_mock(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        async_app="""
        async def fetch_remote(url: str, timeout: int = 10) -> str:
            return "ok"
        """
    )
    pytester.makepyfile("""
        import asyncio
        from unittest.mock import patch
        import async_app

        @patch("async_app.fetch_remote", return_value="mocked")
        def test_async_signature_drift(mock_remote):
            # Extra unexpected argument
            asyncio.run(async_app.fetch_remote("https://api.test", extra=123))
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*Mockrot detected rotting mock (signature_mismatch):*",
            "*unexpected keyword argument 'extra'*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1


def test_classmethod_signature_drift(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        domain="""
        class UserRegistry:
            @classmethod
            def register(cls, username: str, *, role: str = "member") -> str:
                return f"{username}:{role}"
        """
    )
    pytester.makepyfile("""
        from unittest.mock import patch
        from domain import UserRegistry

        @patch.object(UserRegistry, "register", return_value="ok")
        def test_classmethod_drift(mock_reg):
            # Missing required 'username' argument
            UserRegistry.register(unknown_kwarg=True)
    """)

    result = pytester.runpytest("--mockrot=strict")
    result.stdout.fnmatch_lines(
        [
            "*Mockrot detected rotting mock (signature_mismatch):*",
            "*missing a required argument*username*",
            "*1 failed*",
        ]
    )
    assert result.ret == 1
