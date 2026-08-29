"""Custom exceptions."""
from __future__ import annotations


class CategoryNotFoundError(Exception):
    """Raised by CategoryNotFoundError."""


class ProductNotFoundError(Exception):
    """Raised by ProductNotFoundError."""


class InvalidCategoryException(Exception):
    """Raised by InvalidCategoryException."""


class CategoryNotEmptyError(Exception):
    """Raised by CategoryNotEmptyError."""

