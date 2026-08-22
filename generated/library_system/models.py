"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Book:
    title: str
    isbn: str
    published_year: int
    available_copies: int
    id: Optional[int] = None


@dataclass
class Author:
    name: str
    id: Optional[int] = None
    birth_year: Optional[int] = None
    biography: Optional[str] = None


@dataclass
class Member:
    name: str
    email: str
    is_active: bool
    id: Optional[int] = None
    membership_date: Optional[date] = None


@dataclass
class Loan:
    book_id: int
    member_id: int
    loan_date: datetime
    due_date: datetime
    status: str
    id: Optional[int] = None
    return_date: Optional[datetime] = None

