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
    project_id: int
    title: str
    priority: int
    status: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None
    due_date: Optional[date] = None


@dataclass
class Priority:
    name: str
    value: int
    id: Optional[int] = None


@dataclass
class Status:
    name: str
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Priority": [("name",)],
    "Status": [("name",)],
}

