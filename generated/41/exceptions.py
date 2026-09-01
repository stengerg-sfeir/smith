"""Custom exceptions."""
from __future__ import annotations


class BookNotFoundError(Exception):
    """Raised by BookNotFoundError."""


class MemberNotFoundError(Exception):
    """Raised by MemberNotFoundError."""


class LoanNotFoundError(Exception):
    """Raised by LoanNotFoundError."""


class InvalidLoanException(Exception):
    """Raised by InvalidLoanException."""


class BookAlreadyBorrowedException(Exception):
    """Raised by BookAlreadyBorrowedException."""


class BookNotAvailableException(Exception):
    """Raised by BookNotAvailableException."""


class ValidationError(Exception):
    """Raised by ValidationError."""

