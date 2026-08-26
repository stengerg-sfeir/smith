"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
    status: str
    priority: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None
    due_date: Optional[date] = None

