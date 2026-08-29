"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Department:
    name: str
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Employee:
    first_name: str
    last_name: str
    email: str
    department_id: int
    hire_date: date
    is_active: bool
    id: Optional[int] = None

