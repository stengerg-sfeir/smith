"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class OrderAlreadyExistsError(Exception):
    """Raised by OrderAlreadyExistsError."""


class ProductNotFoundError(Exception):
    """Raised by ProductNotFoundError."""


class InvalidQuantityError(Exception):
    """Raised by InvalidQuantityError."""


class InvalidPriceError(Exception):
    """Raised by InvalidPriceError."""

