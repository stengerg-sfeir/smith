"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class InvalidStatusError(Exception):
    """Raised by InvalidStatusError."""


class TaskAlreadyExistsError(Exception):
    """Raised by TaskAlreadyExistsError."""

