"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class ExternalServiceUnavailableError(Exception):
    """Raised by ExternalServiceUnavailableError."""


class ValidationException(Exception):
    """Raised by ValidationException."""

