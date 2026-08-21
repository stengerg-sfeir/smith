"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Category:
    name: str
    id: Optional[int] = None
    description: Optional[str] = None
    monthly_budget: Optional[int] = None
    icon: Optional[str] = None


@dataclass
class Expense:
    amount_cents: int
    description: str
    expense_date: str
    category_id: int
    payment_method: str
    is_recurring: bool
    id: Optional[int] = None


@dataclass
class Budget:
    category_id: int
    month: str
    amount_limit_cents: int
    id: Optional[int] = None

