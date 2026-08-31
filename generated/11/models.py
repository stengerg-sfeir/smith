"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    publication_year: int
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Book": [("isbn",)],
}

