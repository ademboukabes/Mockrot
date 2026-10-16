"""Unit tests for Rich terminal reporter (F8)."""

from __future__ import annotations

import importlib
import io
from typing import Any

import mockrot.reporter
from mockrot.models import MockSite, Violation, ViolationKind
from mockrot.reporter import (
    build_violation_table,
    format_terminal_summary,
    format_violation_for_strict,
    format_violation_title,
    render_terminal_summary,
)

importlib.reload(mockrot.reporter)


def make_site() -> MockSite:
    return MockSite(file_path="tests/test_demo.py", line_number=42, test_name="test_checkout")


def test_format_violation_title_all_kinds() -> None:
    assert format_violation_title(ViolationKind.SIGNATURE_MISMATCH) == "Call Signature Drift"
    assert format_violation_title(ViolationKind.RETURN_TYPE_DRIFT) == "Return Type Drift"
    assert format_violation_title(ViolationKind.ASYNC_MISMATCH) == "Async / Await Mismatch"
    assert format_violation_title(ViolationKind.ZOMBIE_FIELD) == "Zombie Field in Mocked Dictionary"


def test_build_violation_table_for_zombie_field() -> None:
    v = Violation(
        site=make_site(),
        target_name="app.get_user",
        kind=ViolationKind.ZOMBIE_FIELD,
        message="Zombie field 'old_token' detected",
        expected="Declared fields: ['id', 'name']",
        actual="Unexpected key 'old_token' with value 'xyz'",
    )
    table = build_violation_table(v)
    assert table is not None
    assert table.title == "Zombie Field Details"
    assert len(table.columns) == 3


def test_build_violation_table_for_return_type_dict_drift() -> None:
    v = Violation(
        site=make_site(),
        target_name="app.get_user",
        kind=ViolationKind.RETURN_TYPE_DRIFT,
        message="dict: {'bad': 1} does not match User",
        expected="User",
        actual="dict: {'bad': 1}",
    )
    table = build_violation_table(v)
    assert table is not None
    assert table.title == "Type Drift Comparison"


def test_build_violation_table_returns_none_for_signature_mismatch() -> None:
    v = Violation(
        site=make_site(),
        target_name="app.calc",
        kind=ViolationKind.SIGNATURE_MISMATCH,
        message="Missing argument",
        expected="(a: int)",
        actual="args=()",
    )
    assert build_violation_table(v) is None


def test_format_violation_for_strict() -> None:
    v = Violation(
        site=make_site(),
        target_name="app.calc",
        kind=ViolationKind.SIGNATURE_MISMATCH,
        message="Missing required positional argument: 'x'",
        expected="(x: int)",
        actual="args=()",
    )
    msg = format_violation_for_strict(v)
    assert "Mockrot detected rotting mock (signature_mismatch)" in msg
    assert "tests/test_demo.py:42" in msg
    assert "app.calc" in msg


def test_format_terminal_summary_empty_violations_returns_empty_string() -> None:
    assert format_terminal_summary([]) == ""


def test_format_terminal_summary_renders_sections_and_tables() -> None:
    v1 = Violation(
        site=make_site(),
        target_name="app.calc",
        kind=ViolationKind.SIGNATURE_MISMATCH,
        message="missing required argument",
        expected="(x: int)",
        actual="args=()",
    )
    v2 = Violation(
        site=make_site(),
        target_name="app.user",
        kind=ViolationKind.ZOMBIE_FIELD,
        message="Zombie key found",
        expected="['id']",
        actual="Unexpected key 'extra' with value 123",
    )

    output = format_terminal_summary([v1, v2], total_tests=10)
    assert "MOCKROT REPORT - 2 Rotting Mock(s) Detected across 10 test(s)" in output
    assert "Call Signature Drift: app.calc" in output
    assert "Zombie Field Details" in output
    assert "Tip: Fix these 2 mock(s)" in output


def test_render_terminal_summary_writes_to_file_like_target() -> None:
    v = Violation(
        site=make_site(),
        target_name="app.calc",
        kind=ViolationKind.SIGNATURE_MISMATCH,
        message="missing required argument",
        expected="(x: int)",
        actual="args=()",
    )
    buf = io.StringIO()
    render_terminal_summary([v], total_tests=1, output_file=buf)
    content = buf.getvalue()
    assert "MOCKROT REPORT" in content
    assert "app.calc" in content


class MockTerminalWriter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_line(self, line: str) -> None:
        self.lines.append(line)


def test_render_terminal_summary_writes_to_write_line_target() -> None:
    v = Violation(
        site=make_site(),
        target_name="app.calc",
        kind=ViolationKind.SIGNATURE_MISMATCH,
        message="missing required argument",
        expected="(x: int)",
        actual="args=()",
    )
    writer = MockTerminalWriter()
    render_terminal_summary([v], total_tests=1, output_file=writer)
    assert len(writer.lines) > 0
    joined = "\n".join(writer.lines)
    assert "MOCKROT REPORT" in joined


def test_render_terminal_summary_default_stdout(capsys: Any) -> None:
    v = Violation(
        site=MockSite(file_path="foo.py", line_number=1, test_name=""),
        target_name="app.calc",
        kind=ViolationKind.ASYNC_MISMATCH,
        message="async required",
        expected="coroutine",
        actual="int",
    )
    render_terminal_summary([v], total_tests=0, output_file=None)
    captured = capsys.readouterr()  # pyright: ignore[reportUnknownMemberType]
    assert "MOCKROT REPORT" in captured.out
    assert "foo.py:1" in captured.out


def test_build_violation_table_scalar_return_type_drift_returns_none() -> None:
    v = Violation(
        site=make_site(),
        target_name="app.calc",
        kind=ViolationKind.RETURN_TYPE_DRIFT,
        message="type mismatch",
        expected="int",
        actual="str: 'hello'",
    )
    assert build_violation_table(v) is None


def test_format_violation_for_strict_without_test_name() -> None:
    v = Violation(
        site=MockSite(file_path="foo.py", line_number=10, test_name=""),
        target_name="app.calc",
        kind=ViolationKind.SIGNATURE_MISMATCH,
        message="error",
        expected="int",
        actual="str",
    )
    msg = format_violation_for_strict(v)
    assert "foo.py:10\n" in msg
