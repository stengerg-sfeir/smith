"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class UnauthorizedError(Exception):
    """Raised by UnauthorizedError."""


class ConflictError(Exception):
    """Raised by ConflictError."""


class InvalidStateError(Exception):
    """Raised by InvalidStateError."""

