"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Category:
    name: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Product:
    name: str
    price: float
    category_id: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None

