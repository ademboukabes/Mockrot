"""Exceptions hierarchy for Mockrot."""

from __future__ import annotations


class MockrotError(Exception):
    """Base exception for all Mockrot runtime and configuration errors."""


class ContractExtractionError(MockrotError):
    """Raised when extraction of signature or type hints fails unexpectedly."""


class ContractValidationError(MockrotError):
    """Raised when a mock interaction violates the target contract."""


class ConfigurationError(MockrotError):
    """Raised when Mockrot configuration in pyproject.toml or CLI is invalid."""
