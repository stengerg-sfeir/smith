"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DepartmentAlreadyExistsError(Exception):
    """Raised by DepartmentAlreadyExistsError."""


class EmployeeAlreadyExistsError(Exception):
    """Raised by EmployeeAlreadyExistsError."""


class InvalidDepartmentIdError(Exception):
    """Raised by InvalidDepartmentIdError."""


class InvalidEmployeeIdError(Exception):
    """Raised by InvalidEmployeeIdError."""

