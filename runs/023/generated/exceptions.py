"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class UnauthorizedError(Exception):
    """Raised by UnauthorizedError."""


class DuplicateEntryError(Exception):
    """Raised by DuplicateEntryError."""


class InvalidTagError(Exception):
    """Raised by InvalidTagError."""


class PostSearchError(Exception):
    """Raised by PostSearchError."""

