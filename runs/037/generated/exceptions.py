"""Custom exceptions."""
from __future__ import annotations


class ProjectNotFoundError(Exception):
    """Raised by ProjectNotFoundError."""


class TaskNotFoundError(Exception):
    """Raised by TaskNotFoundError."""


class ValidationException(Exception):
    """Raised by ValidationException."""


class AtomicOperationFailedException(Exception):
    """Raised by AtomicOperationFailedException."""

