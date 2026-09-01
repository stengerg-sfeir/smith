"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Customer:
    name: str
    email: str
    id: Optional[int] = None


@dataclass
class Product:
    name: str
    price: float
    stock_quantity: int
    created_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Order:
    customer_id: int
    status: str
    total_amount: float
    created_at: datetime
    id: Optional[int] = None
    cancelled_at: Optional[datetime] = None


@dataclass
class OrderProduct:
    order_id: int
    product_id: int
    quantity: int


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
    "OrderProduct": [("order_id", "product_id")],
}


TABLE_NAMES: Dict[str, str] = {
    "OrderProduct": "order_products",
}

