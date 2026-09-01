"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    available: bool
    id: Optional[int] = None


@dataclass
class Member:
    name: str
    email: str
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class BorrowRecord:
    book_id: int
    member_id: int
    borrow_date: datetime
    id: Optional[int] = None
    return_date: Optional[datetime] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Book": [("isbn",)],
    "Member": [("email",)],
}


TABLE_NAMES: Dict[str, str] = {
    "BorrowRecord": "borrow_records",
}

