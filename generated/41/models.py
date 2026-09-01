"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    available_copies: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Member:
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    phone: Optional[str] = None
    membership_since: Optional[date] = None


@dataclass
class Loan:
    member_id: int
    book_id: int
    loan_date: datetime
    due_date: datetime
    is_returned: bool
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    return_date: Optional[datetime] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Book": [("isbn",)],
}

