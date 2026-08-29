"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class DatabaseConnectionError(Exception):
    """Raised by DatabaseConnectionError."""


class DuplicateNoteError(Exception):
    """Raised by DuplicateNoteError."""

