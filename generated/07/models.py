"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    publication_year: int
    pages: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    genre: Optional[str] = None

