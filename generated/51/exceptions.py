"""Custom exceptions."""
from __future__ import annotations


class SKUConflictError(Exception):
    """Raised by SKUConflictError."""


class InvalidSKUError(Exception):
    """Raised by InvalidSKUError."""


class CategoryMismatchError(Exception):
    """Raised by CategoryMismatchError."""

