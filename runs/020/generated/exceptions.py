"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DatabaseError(Exception):
    """Raised by DatabaseError."""


class SalesReportError(Exception):
    """Raised by SalesReportError."""

