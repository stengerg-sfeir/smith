"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class UnauthorizedError(Exception):
    """Raised by UnauthorizedError."""


class InvalidStatusError(Exception):
    """Raised by InvalidStatusError."""


class InvalidPriorityError(Exception):
    """Raised by InvalidPriorityError."""

