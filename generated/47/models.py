"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Project:
    name: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Task:
    title: str
    project_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None


@dataclass
class Person:
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    role: Optional[str] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Person": [("email",)],
}


TABLE_NAMES: Dict[str, str] = {
    "Person": "people",
}

