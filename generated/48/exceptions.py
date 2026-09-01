"""Custom exceptions."""
from __future__ import annotations


class BookNotFoundError(Exception):
    """Raised by BookNotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class DuplicateBookError(Exception):
    """Raised by DuplicateBookError."""


class BookAlreadyExistsError(Exception):
    """Raised by BookAlreadyExistsError."""

