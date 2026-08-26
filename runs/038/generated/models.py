"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    email: str
    password_hash: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Document:
    title: str
    content: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None

