"""Custom exceptions."""
from __future__ import annotations


class DocumentNotFoundError(Exception):
    """Raised by DocumentNotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class PermissionDeniedError(Exception):
    """Raised by PermissionDeniedError."""


class DocumentAlreadyExistsError(Exception):
    """Raised by DocumentAlreadyExistsError."""


class InvalidDocumentFormatError(Exception):
    """Raised by InvalidDocumentFormatError."""

