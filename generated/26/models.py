"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
class Loan:
    member_id: int
    book_id: int
    loan_date: datetime
    due_date: datetime
    status: str
    id: Optional[int] = None
    return_date: Optional[datetime] = None

