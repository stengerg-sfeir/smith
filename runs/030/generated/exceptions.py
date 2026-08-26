"""Custom exceptions."""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised when a resource is not found."""
    def __init__(self, description: str, status: int, priority: int, due_date: str, created_at: str, updated_at: str):
        self.description = description
        self.status = status
        self.priority = priority
        self.due_date = due_date
        self.created_at = created_at
        self.updated_at = updated_at
        super().__init__(description)


class ValidationException(Exception):
    """Raised when validation fails."""
    def __init__(self, description: str, status: int, priority: int, due_date: str, created_at: str, updated_at: str):
        self.description = description
        self.status = status
        self.priority = priority
        self.due_date = due_date
        self.created_at = created_at
        self.updated_at = updated_at
        super().__init__(description)


class DatabaseConnectionError(Exception):
    """Raised when database connection fails."""
    def __init__(self, description: str, status: int, priority: int, due_date: str, created_at: str, updated_at: str):
        self.description = description
        self.status = status
        self.priority = priority
        self.due_date = due_date
        self.created_at = created_at
        self.updated_at = updated_at
        super().__init__(description)


class TaskAlreadyExistsError(Exception):
    """Raised when trying to create a task that already exists."""
    def __init__(self, description: str, status: int, priority: int, due_date: str, created_at: str, updated_at: str):
        self.description = description
        self.status = status
        self.priority = priority
        self.due_date = due_date
        self.created_at = created_at
        self.updated_at = updated_at
        super().__init__(description)


class TaskNotFoundException(Exception):
    """Raised when a task is not found."""
    def __init__(self, description: str, status: int, priority: int, due_date: str, created_at: str, updated_at: str):
        self.description = description
        self.status = status
        self.priority = priority
        self.due_date = due_date
        self.created_at = created_at
        self.updated_at = updated_at
        super().__init__(description)
