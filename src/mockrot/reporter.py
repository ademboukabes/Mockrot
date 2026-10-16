"""Rich-based terminal reporting for Mockrot contract violations."""

from __future__ import annotations

import io
import sys
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from mockrot.models import Violation, ViolationKind

if TYPE_CHECKING:
    from collections.abc import Sequence


def format_violation_title(kind: ViolationKind) -> str:
    """Return a human-readable title for a violation kind."""
    if kind == ViolationKind.SIGNATURE_MISMATCH:
        return "Call Signature Drift"
    if kind == ViolationKind.RETURN_TYPE_DRIFT:
        return "Return Type Drift"
    if kind == ViolationKind.ASYNC_MISMATCH:
        return "Async / Await Mismatch"
    if kind == ViolationKind.ZOMBIE_FIELD:
        return "Zombie Field in Mocked Dictionary"
    return "Contract Violation"


def build_violation_table(violation: Violation) -> Table | None:
    """Build a detailed Rich Table for dictionary and return type violations."""
    if violation.kind == ViolationKind.ZOMBIE_FIELD:
        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            title="Zombie Field Details",
        )
        table.add_column("Field", style="bold cyan")
        table.add_column(f"Mocked Value ({violation.site.file_path}:{violation.site.line_number})")
        table.add_column("Contract Status", style="bold red")

        raw_key = violation.actual.split("with value")[0].replace("Unexpected key", "").strip(" '")
        table.add_row(
            raw_key,
            violation.actual,
            "Unknown field (not declared on real model)",
        )
        return table

    if violation.kind == ViolationKind.RETURN_TYPE_DRIFT and (
        "dict" in violation.actual or "{" in violation.actual
    ):
        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            title="Type Drift Comparison",
        )
        table.add_column("Expected Contract", style="bold green")
        table.add_column("Actual Mock Output", style="bold red")
        table.add_row(violation.expected, violation.actual)
        return table

    return None


def format_violation_for_strict(violation: Violation) -> str:
    """Format a single violation message for pytest.fail in strict mode."""
    site_info = (
        f"{violation.site.file_path}:{violation.site.line_number} ({violation.site.test_name})"
        if violation.site.test_name
        else f"{violation.site.file_path}:{violation.site.line_number}"
    )
    return (
        f"\nMockrot detected rotting mock ({violation.kind.value}):\n"
        f"  Target:   {violation.target_name}\n"
        f"  Site:     {site_info}\n"
        f"  Error:    {violation.message}\n"
        f"  Expected: {violation.expected}\n"
        f"  Actual:   {violation.actual}"
    )


def format_terminal_summary(
    violations: Sequence[Violation],
    total_tests: int = 0,
    force_terminal: bool | None = None,
) -> str:
    """Format Rich terminal summary table and details into a string."""
    if not violations:
        return ""

    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=force_terminal,
        width=100,
        highlight=False,
    )
    count = len(violations)
    test_str = f" across {total_tests} test(s)" if total_tests > 0 else ""

    console.print(
        f"\n[bold red]MOCKROT REPORT - {count} Rotting Mock(s) Detected{test_str}[/bold red]\n"
    )

    for idx, v in enumerate(violations, start=1):
        title = format_violation_title(v.kind)
        site_str = (
            f"{v.site.file_path}:{v.site.line_number} ({v.site.test_name})"
            if v.site.test_name
            else f"{v.site.file_path}:{v.site.line_number}"
        )
        escaped_kind = escape(f"[{v.kind.value}]")
        escaped_target = escape(v.target_name)
        console.print(
            f"[bold red][{idx}/{count}] {escaped_kind} {title}: {escaped_target} in "
            f"[underline]{site_str}[/underline][/bold red]"
        )
        console.print(f"  [cyan]├─ Target:   {escaped_target}[/cyan]")
        console.print(f"  [cyan]├─ Expected: {escape(v.expected)}[/cyan]")
        console.print(f"  [cyan]├─ Actual:   {escape(v.actual)}[/cyan]")
        console.print(f"  [cyan]└─ Error:    {escape(v.message)}[/cyan]")

        table = build_violation_table(v)
        if table is not None:
            console.print()
            console.print(table)
        console.print()

    console.rule(style="red")
    tip = f"Tip: Fix these {count} mock(s) to prevent false-positive unit tests in CI."
    summary = f"{count} rotting mock(s) detected. Fix these mocks to prevent false positives in CI."
    console.print(f"[bold yellow]{tip}[/bold yellow]")
    console.print(f"[bold red]{summary}[/bold red]\n")

    return buffer.getvalue()


def render_terminal_summary(
    violations: Sequence[Violation],
    total_tests: int = 0,
    output_file: Any = None,
    force_terminal: bool | None = None,
) -> None:
    """Render Rich terminal summary to the provided output file or stdout."""
    summary_text = format_terminal_summary(
        violations=violations,
        total_tests=total_tests,
        force_terminal=force_terminal,
    )
    target: Any = output_file if output_file is not None else sys.stdout
    write_fn = getattr(target, "write", None)
    if callable(write_fn):
        write_fn(summary_text)
    else:
        write_line_fn = getattr(target, "write_line", None)
        if callable(write_line_fn):
            for line in summary_text.splitlines():
                write_line_fn(line)
