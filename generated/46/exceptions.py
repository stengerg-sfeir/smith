"""Custom exceptions."""
from __future__ import annotations


class ClientNotFoundError(Exception):
    """Raised by ClientNotFoundError."""


class InvoiceNotFoundError(Exception):
    """Raised by InvoiceNotFoundError."""


class PaymentNotFoundError(Exception):
    """Raised by PaymentNotFoundError."""


class InvalidClientDataError(Exception):
    """Raised by InvalidClientDataError."""


class InvalidInvoiceDataError(Exception):
    """Raised by InvalidInvoiceDataError."""


class InvalidPaymentDataError(Exception):
    """Raised by InvalidPaymentDataError."""


class OutOfDateInvoiceError(Exception):
    """Raised by OutOfDateInvoiceError."""


class DuplicateInvoiceError(Exception):
    """Raised by DuplicateInvoiceError."""


class ValidationError(Exception):
    """Raised by ValidationError."""

