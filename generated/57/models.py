"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Document:
    title: str
    content: str
    file_path: str
    created_at: datetime
    updated_at: datetime
    version: int
    id: Optional[int] = None
    author_id: Optional[int] = None

