"""Custom exceptions."""
from __future__ import annotations


class InvalidOrderLineException(Exception):
    """Raised by InvalidOrderLineException."""


class OrderCreationFailedException(Exception):
    """Raised by OrderCreationFailedException."""


class ValidationError(Exception):
    """Raised by ValidationError."""

