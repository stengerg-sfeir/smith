"""Custom exceptions."""
from __future__ import annotations


class EmployeeNotFoundError(Exception):
    """Raised by EmployeeNotFoundError."""


class DepartmentNotFoundError(Exception):
    """Raised by DepartmentNotFoundError."""


class InvalidEmployeeDataError(Exception):
    """Raised by InvalidEmployeeDataError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class PermissionDeniedError(Exception):
    """Raised by PermissionDeniedError."""

