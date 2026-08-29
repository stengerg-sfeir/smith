"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class ImportError(Exception):
    """Raised by ImportError."""


class DuplicateEntryError(Exception):
    """Raised by DuplicateEntryError."""

