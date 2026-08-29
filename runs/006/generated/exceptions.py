"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DuplicateEntryError(Exception):
    """Raised by DuplicateEntryError."""


class OutOfStockError(Exception):
    """Raised by OutOfStockError."""


class InvalidPriceError(Exception):
    """Raised by InvalidPriceError."""


class InvalidQuantityError(Exception):
    """Raised by InvalidQuantityError."""

