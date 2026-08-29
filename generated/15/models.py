"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    name: str
    price: float
    quantity: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None

