"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class OrderNotFoundError(Exception):
    """Raised by OrderNotFoundError."""


class ProductNotFoundError(Exception):
    """Raised by ProductNotFoundError."""


class InvalidProductQuantityError(Exception):
    """Raised by InvalidProductQuantityError."""


class InvalidOrderStatusError(Exception):
    """Raised by InvalidOrderStatusError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DatabaseConnectionError(Exception):
    """Raised by DatabaseConnectionError."""


class AtomicOperationFailedError(Exception):
    """Raised by AtomicOperationFailedError."""

