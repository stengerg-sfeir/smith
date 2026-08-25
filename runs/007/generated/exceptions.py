"""Custom exceptions."""
from __future__ import annotations


class BookNotFoundError(Exception):
    """Raised by BookNotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class BookAlreadyExistsError(Exception):
    """Raised by BookAlreadyExistsError."""


class InvalidSearchQueryError(Exception):
    """Raised by InvalidSearchQueryError."""

