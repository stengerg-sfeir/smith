"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised by NotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class OutOfStockError(Exception):
    """Raised by OutOfStockError."""


class InvalidDiscountError(Exception):
    """Raised by InvalidDiscountError."""


class OrderCancellationError(Exception):
    """Raised by OrderCancellationError."""


class TaxCalculationError(Exception):
    """Raised by TaxCalculationError."""


class StockRestorationError(Exception):
    """Raised by StockRestorationError."""


class ReportingError(Exception):
    """Raised by ReportingError."""


class ExportError(Exception):
    """Raised by ExportError."""

