"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    name: str
    price: float
    stock_quantity: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Sale:
    product_id: int
    quantity: int
    sale_price: float
    sold_at: datetime
    id: Optional[int] = None

