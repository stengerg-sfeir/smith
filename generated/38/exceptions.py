"""Custom exceptions."""
from __future__ import annotations


class AuthenticationError(Exception):
    """Raised by AuthenticationError."""


class PermissionError(Exception):
    """Raised by PermissionError."""


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""

