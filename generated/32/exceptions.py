"""Custom exceptions."""
from __future__ import annotations


class OrderNotFoundError(Exception):
    """Raised by OrderNotFoundError."""


class InvalidStateTransitionError(Exception):
    """Raised by InvalidStateTransitionError."""


class OrderAlreadyCancelledError(Exception):
    """Raised by OrderAlreadyCancelledError."""


class OrderAlreadyShippedError(Exception):
    """Raised by OrderAlreadyShippedError."""


class ValidationError(Exception):
    """Raised by ValidationError."""

