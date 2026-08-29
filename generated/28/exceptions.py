"""Custom exceptions."""
from __future__ import annotations


class InvoiceNotFoundError(Exception):
    """Raised by InvoiceNotFoundError."""


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class ProductNotFoundError(Exception):
    """Raised by ProductNotFoundError."""


class InvalidQuantityError(Exception):
    """Raised by InvalidQuantityError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class InvoiceTotalCalculationError(Exception):
    """Raised by InvoiceTotalCalculationError."""

