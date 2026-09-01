"""Custom exceptions."""
from __future__ import annotations


class EventFullException(Exception):
    """Raised by EventFullException."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class EventNotFoundException(Exception):
    """Raised by EventNotFoundException."""

