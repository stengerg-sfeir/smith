"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Product:
    name: str
    price: float
    stock_quantity: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Customer:
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class Sale:
    customer_id: int
    product_id: int
    quantity: int
    total_price: float
    sale_date: datetime
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
}

