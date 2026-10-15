"""Standalone CLI entry point for Mockrot (delegates to pytest)."""

from __future__ import annotations

import sys

import pytest


def main(argv: list[str] | None = None) -> int:
    """Run pytest with Mockrot enabled by default."""
    args = list(sys.argv[1:] if argv is None else argv)

    # Ensure --mockrot flag is injected if not explicitly provided
    has_mockrot_flag = any(arg.startswith("--mockrot") for arg in args)
    if not has_mockrot_flag:
        args.insert(0, "--mockrot=warn")

    return int(pytest.main(args))


if __name__ == "__main__":
    sys.exit(main())
