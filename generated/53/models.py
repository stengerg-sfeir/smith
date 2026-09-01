"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    customer_id: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Product:
    name: str
    stock_quantity: int
    price: float
    id: Optional[int] = None


@dataclass
class OrderItem:
    order_id: int
    product_id: int
    quantity: int
    id: Optional[int] = None

