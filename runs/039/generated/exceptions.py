"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class PermissionDeniedError(Exception):
    """Raised by PermissionDeniedError."""


class UnauthorizedError(Exception):
    """Raised by UnauthorizedError."""


class OrderCreationFailedError(Exception):
    """Raised by OrderCreationFailedError."""

