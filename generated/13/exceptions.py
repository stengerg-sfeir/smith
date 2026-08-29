"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DuplicateSkuError(Exception):
    """Raised by DuplicateSkuError."""


class OutOfStockError(Exception):
    """Raised by OutOfStockError."""


class InvalidCategoryError(Exception):
    """Raised by InvalidCategoryError."""

