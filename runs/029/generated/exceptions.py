"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class OrderNotFoundError(Exception):
    """Raised by OrderNotFoundError."""


class InvalidCustomerDataError(Exception):
    """Raised by InvalidCustomerDataError."""


class InvalidOrderDataError(Exception):
    """Raised by InvalidOrderDataError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DatabaseConnectionError(Exception):
    """Raised by DatabaseConnectionError."""


class OrderAlreadyExistsError(Exception):
    """Raised by OrderAlreadyExistsError."""


class InsufficientFundsError(Exception):
    """Raised by InsufficientFundsError."""

