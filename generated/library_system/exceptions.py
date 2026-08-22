"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class LoanAlreadyReturnedError(Exception):
    """Raised by LoanAlreadyReturnedError."""


class BookNotAvailableError(Exception):
    """Raised by BookNotAvailableError."""


class InvalidLoanStatusError(Exception):
    """Raised by InvalidLoanStatusError."""


class MemberNotActiveError(Exception):
    """Raised by MemberNotActiveError."""


class InvalidQueryError(Exception):
    """Raised by InvalidQueryError."""


class DuplicateEmailError(Exception):
    """Raised by DuplicateEmailError."""


class InvalidBookIdError(Exception):
    """Raised by InvalidBookIdError."""


class InvalidMemberIdError(Exception):
    """Raised by InvalidMemberIdError."""


class InvalidLoanIdError(Exception):
    """Raised by InvalidLoanIdError."""


class OverdueLoanError(Exception):
    """Raised by OverdueLoanError."""

