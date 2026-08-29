"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class OrderNotFoundError(Exception):
    """Raised by OrderNotFoundError."""


class InvalidOrderStatusError(Exception):
    """Raised by InvalidOrderStatusError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DuplicateCustomerError(Exception):
    """Raised by DuplicateCustomerError."""


class OrderDateValidationError(Exception):
    """Raised by OrderDateValidationError."""

