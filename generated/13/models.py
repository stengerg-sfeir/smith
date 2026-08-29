"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    sku: str
    name: str
    category: str
    price: float
    stock_quantity: int
    id: Optional[int] = None

