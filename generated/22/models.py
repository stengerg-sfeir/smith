"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    customer_name: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Product:
    name: str
    price: float
    created_at: datetime
    id: Optional[int] = None


@dataclass
class OrderItem:
    order_id: int
    product_id: int
    quantity: int
    unit_price: float
    created_at: datetime
    id: Optional[int] = None

