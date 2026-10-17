"""End-to-end integration tests for transparent interception using pytester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_interceptor_runs_transparently_under_pytest_mockrot(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile("""
        import math
        from unittest.mock import patch

        @patch("math.sqrt", return_value=999)
        def test_patch_transparent(mock_sqrt):
            val = math.sqrt(4)
            assert val == 999
            mock_sqrt.assert_called_once_with(4)

        def test_context_manager_transparent():
            with patch("math.floor", return_value=42) as mock_floor:
                val = math.floor(3.14)
                assert val == 42
                assert mock_floor.call_count == 1
    """)

    result = pytester.runpytest("--mockrot=warn")
    result.stdout.fnmatch_lines(
        [
            "*mockrot: active (mode=warn)*",
            "*2 passed*",
        ]
    )
    assert result.ret == 0


def test_interceptor_does_not_affect_tests_when_disabled(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile("""
        import math
        from unittest.mock import patch

        @patch("math.sqrt", return_value=123)
        def test_without_mockrot(mock_sqrt):
            assert math.sqrt(16) == 123
    """)

    result = pytester.runpytest()
    assert "mockrot: active" not in result.stdout.str()
    result.stdout.fnmatch_lines(
        [
            "*1 passed*",
        ]
    )
    assert result.ret == 0


def test_behavioral_transparency_equivalence_with_and_without_mockrot(
    pytester: pytest.Pytester,
) -> None:
    """Non-regression test: ensure suites with complex monkeypatching behave identically."""
    pytester.makepyfile("""
        import sys

        class CustomRecorder:
            def __init__(self):
                self.calls = []
            def __call__(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return 42

        class Worker:
            def do_work(self):
                return 0

        class DataSource:
            def read_data(self):
                return "stream-data"

        class Consumer:
            def read_data(self):
                return "initial"

        def test_custom_callable_attributes(monkeypatch):
            recorder = CustomRecorder()
            w = Worker()
            monkeypatch.setattr(w, "do_work", recorder)
            assert w.do_work("task-1") == 42
            assert len(recorder.calls) == 1
            assert recorder.calls[0][0] == ("task-1",)

        def test_bound_method_on_class(monkeypatch):
            source = DataSource()
            monkeypatch.setattr(Consumer, "read_data", source.read_data)
            c = Consumer()
            assert c.read_data() == "stream-data"

        def test_patch_sys_stdin_buffer(monkeypatch):
            monkeypatch.setattr(sys.stdin.buffer, "read", lambda *a: b"data")
            assert sys.stdin.buffer.read() == b"data"
    """)

    # 1. Run without mockrot
    res_without = pytester.runpytest()
    assert res_without.ret == 0
    res_without.stdout.fnmatch_lines(["*3 passed*"])

    # 2. Run with mockrot=warn
    res_with = pytester.runpytest("--mockrot=warn")
    assert res_with.ret == 0
    res_with.stdout.fnmatch_lines(["*3 passed*"])
