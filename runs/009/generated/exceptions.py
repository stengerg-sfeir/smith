"""Custom exceptions."""
from __future__ import annotations


class InvalidEmailError(Exception):
    """Raised by InvalidEmailError."""


class AgeOutOfRangeError(Exception):
    """Raised by AgeOutOfRangeError."""


class NegativeSalaryError(Exception):
    """Raised by NegativeSalaryError."""


class EmployeeNotFoundError(Exception):
    """Raised by EmployeeNotFoundError."""


class DatabaseConnectionError(Exception):
    """Raised by DatabaseConnectionError."""

