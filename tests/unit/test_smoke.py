"""Smoke tests for package metadata, models, and errors."""

from __future__ import annotations

import importlib

import pytest

import mockrot
import mockrot.models
from mockrot.errors import ContractValidationError, MockrotError
from mockrot.models import MockSite, Violation, ViolationKind


def test_exposes_version_when_package_is_imported() -> None:
    importlib.reload(mockrot)
    importlib.reload(mockrot.models)
    assert isinstance(mockrot.__version__, str)
    assert mockrot.__version__ == "0.1.0"


def test_instantiates_violation_model_when_valid_attributes_provided() -> None:
    site = MockSite(file_path="tests/test_demo.py", line_number=42, test_name="test_fn")
    violation = Violation(
        site=site,
        target_name="pkg.service.fn",
        kind=ViolationKind.SIGNATURE_MISMATCH,
        message="Signature mismatch",
        expected="def fn(x: int)",
        actual="fn(y=1)",
    )

    assert violation.site.file_path == "tests/test_demo.py"
    assert violation.site.line_number == 42
    assert violation.kind == ViolationKind.SIGNATURE_MISMATCH


def test_raises_expected_hierarchy_when_mockrot_error_occurs() -> None:
    with pytest.raises(MockrotError) as exc_info:
        raise ContractValidationError("contract failed")

    assert "contract failed" in str(exc_info.value)
