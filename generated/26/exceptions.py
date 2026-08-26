"""Custom exceptions."""
from __future__ import annotations


class BookNotFoundError(Exception):
    """Raised by BookNotFoundError."""


class MemberNotFoundError(Exception):
    """Raised by MemberNotFoundError."""


class LoanNotFoundError(Exception):
    """Raised by LoanNotFoundError."""


class BookAlreadyBorrowedException(Exception):
    """Raised by BookAlreadyBorrowedException."""


class InvalidLoanStateException(Exception):
    """Raised by InvalidLoanStateException."""


class ValidationError(Exception):
    """Raised by ValidationError."""

