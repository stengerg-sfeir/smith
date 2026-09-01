"""Custom exceptions."""
from __future__ import annotations


class BookNotFoundError(Exception):
    """Raised by BookNotFoundError."""


class MemberNotFoundError(Exception):
    """Raised by MemberNotFoundError."""


class BookAlreadyBorrowedException(Exception):
    """Raised by BookAlreadyBorrowedException."""


class InvalidBorrowRequestException(Exception):
    """Raised by InvalidBorrowRequestException."""


class BookNotAvailableException(Exception):
    """Raised by BookNotAvailableException."""


class InvalidReturnRequestException(Exception):
    """Raised by InvalidReturnRequestException."""

