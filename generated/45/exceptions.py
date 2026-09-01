"""Custom exceptions."""
from __future__ import annotations


class RoomNotFoundError(Exception):
    """Raised by RoomNotFoundError."""


class GuestNotFoundError(Exception):
    """Raised by GuestNotFoundError."""


class BookingConflictError(Exception):
    """Raised by BookingConflictError."""


class InvalidDateError(Exception):
    """Raised by InvalidDateError."""


class ValidationError(Exception):
    """Raised by ValidationError."""

