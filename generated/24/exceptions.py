"""Custom exceptions."""
from __future__ import annotations


class ProjectNotFoundError(Exception):
    """Raised by ProjectNotFoundError."""


class TaskNotFoundError(Exception):
    """Raised by TaskNotFoundError."""


class InvalidProjectDataError(Exception):
    """Raised by InvalidProjectDataError."""


class InvalidTaskDataError(Exception):
    """Raised by InvalidTaskDataError."""


class ValidationError(Exception):
    """Raised by ValidationError."""


class PermissionDeniedError(Exception):
    """Raised by PermissionDeniedError."""


class ProjectAlreadyExistsError(Exception):
    """Raised by ProjectAlreadyExistsError."""


class TaskAlreadyExistsError(Exception):
    """Raised by TaskAlreadyExistsError."""

