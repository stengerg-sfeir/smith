"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    name: str
    price: float
    id: Optional[int] = None


@dataclass
class Sale:
    product_id: int
    quantity: int
    sale_date: datetime
    id: Optional[int] = None

