"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Note:
    title: str
    content: str
    created_at: datetime
    id: Optional[int] = None

