"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    publication_year: Optional[int] = None
    genre: Optional[str] = None
    pages: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Book": [("isbn",)],
}

