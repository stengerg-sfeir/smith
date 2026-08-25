"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class InvalidPageSizeError(Exception):
    """Raised by InvalidPageSizeError."""


class InvalidPageNumberError(Exception):
    """Raised by InvalidPageNumberError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DatabaseConnectionError(Exception):
    """Raised by DatabaseConnectionError."""

