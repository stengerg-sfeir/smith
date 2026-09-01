"""Custom exceptions."""
from __future__ import annotations


class StockUnderflowError(Exception):
    """Raised by StockUnderflowError."""


class InvalidProductError(Exception):
    """Raised by InvalidProductError."""


class OutOfStockError(Exception):
    """Raised by OutOfStockError."""


class ValidationError(Exception):
    """Raised by ValidationError."""

