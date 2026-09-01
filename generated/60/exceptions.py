"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class ProductNotFoundError(Exception):
    """Raised by ProductNotFoundError."""


class OrderNotFoundError(Exception):
    """Raised by OrderNotFoundError."""


class InvoiceNotFoundError(Exception):
    """Raised by InvoiceNotFoundError."""


class CategoryNotFoundError(Exception):
    """Raised by CategoryNotFoundError."""


class InvalidOrderStatusError(Exception):
    """Raised by InvalidOrderStatusError."""


class StockInsufficientError(Exception):
    """Raised by StockInsufficientError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class PermissionDeniedError(Exception):
    """Raised by PermissionDeniedError."""


class DuplicateEntryError(Exception):
    """Raised by DuplicateEntryError."""


class InvalidInputError(Exception):
    """Raised by InvalidInputError."""

