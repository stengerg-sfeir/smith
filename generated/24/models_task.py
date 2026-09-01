"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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

