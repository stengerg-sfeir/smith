"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Employee:
    first_name: str
    last_name: str
    email: str
    department_id: int
    hire_date: date
    salary: float
    is_active: bool
    id: Optional[int] = None
    phone: Optional[str] = None
    position: Optional[str] = None


@dataclass
class Department:
    name: str
    id: Optional[int] = None
    description: Optional[str] = None
    manager_id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Department": [("name",)],
    "Employee": [("email",)],
}

