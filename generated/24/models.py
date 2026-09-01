"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Project:
    title: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Task:
    title: str
    status: str
    priority: int
    project_id: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Task": [("project_id", "title")],
}

