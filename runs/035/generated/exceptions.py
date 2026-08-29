"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class TransactionFailedError(Exception):
    """Raised by TransactionFailedError."""


class InvalidProductDataError(Exception):
    """Raised by InvalidProductDataError."""


class BulkUpdateConflictError(Exception):
    """Raised by BulkUpdateConflictError."""

