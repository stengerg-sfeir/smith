"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class DuplicateEntryError(Exception):
    """Raised by DuplicateEntryError."""


class PermissionError(Exception):
    """Raised by PermissionError."""

