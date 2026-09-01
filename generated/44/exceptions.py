"""Custom exceptions."""
from __future__ import annotations


class ProductNotFoundError(Exception):
    """Raised by ProductNotFoundError."""


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class SaleNotFoundError(Exception):
    """Raised by SaleNotFoundError."""


class InvalidQuantityError(Exception):
    """Raised by InvalidQuantityError."""


class OutOfStockError(Exception):
    """Raised by OutOfStockError."""


class ValidationError(Exception):
    """Raised by ValidationError."""

