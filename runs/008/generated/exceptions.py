"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class InvalidArgumentException(Exception):
    """Raised by InvalidArgumentException."""


class OutOfStockException(Exception):
    """Raised by OutOfStockException."""


class FilterException(Exception):
    """Raised by FilterException."""

