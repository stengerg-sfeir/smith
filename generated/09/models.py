"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Employee:
    name: str
    email: str
    age: int
    salary: float
    id: Optional[int] = None

