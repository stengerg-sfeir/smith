"""Custom exceptions."""
from __future__ import annotations


class AppointmentValidationError(Exception):
    """Raised by AppointmentValidationError."""


class InvalidTimeRangeError(Exception):
    """Raised by InvalidTimeRangeError."""


class DuplicateAppointmentError(Exception):
    """Raised by DuplicateAppointmentError."""

