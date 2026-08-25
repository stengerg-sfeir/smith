"""Custom exceptions."""
from __future__ import annotations


class ProjectNotFoundError(Exception):
    """Raised by ProjectNotFoundError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class ProjectAlreadyExistsError(Exception):
    """Raised by ProjectAlreadyExistsError."""


class ProjectSoftDeleteError(Exception):
    """Raised by ProjectSoftDeleteError."""

