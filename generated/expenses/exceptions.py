"""Custom exceptions."""
from __future__ import annotations


class CategoryNotFoundError(Exception):
    """Raised by CategoryNotFoundError."""


class ExpenseNotFoundError(Exception):
    """Raised by ExpenseNotFoundError."""


class BudgetExceededException(Exception):
    """Raised by BudgetExceededException."""

