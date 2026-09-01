"""Custom exceptions."""
from __future__ import annotations


class CustomerNotFoundError(Exception):
    """Raised by CustomerNotFoundError."""


class PurchaseNotFoundError(Exception):
    """Raised by PurchaseNotFoundError."""


class InvalidCustomerIDError(Exception):
    """Raised by InvalidCustomerIDError."""


class InvalidPurchaseIDError(Exception):
    """Raised by InvalidPurchaseIDError."""


class ValidationError(Exception):
    """Raised by ValidationError."""

