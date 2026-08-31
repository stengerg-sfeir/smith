"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Task:
    title: str
    status: str
    created_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None

