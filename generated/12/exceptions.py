"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class EmailAlreadyExistsError(Exception):
    """Raised by EmailAlreadyExistsError."""


class InvalidEmailError(Exception):
    """Raised by InvalidEmailError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DomainFilterError(Exception):
    """Raised by DomainFilterError."""

