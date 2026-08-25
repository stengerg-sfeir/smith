"""Custom exceptions."""
from __future__ import annotations


class BookNotFoundError(Exception):
    """Raised by BookNotFoundError."""


class InvalidISBNException(Exception):
    """Raised by InvalidISBNException."""


class DuplicateISBNException(Exception):
    """Raised by DuplicateISBNException."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class BookUpdateException(Exception):
    """Raised by BookUpdateException."""


class BookDeleteException(Exception):
    """Raised by BookDeleteException."""

