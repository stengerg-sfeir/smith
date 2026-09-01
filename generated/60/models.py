"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Customer:
    name: str
    email: str
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class Product:
    name: str
    price: float
    stock_quantity: int
    category_id: int
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Category:
    name: str
    id: Optional[int] = None


@dataclass
class Order:
    customer_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class OrderItem:
    order_id: int
    product_id: int
    quantity: int


@dataclass
class Invoice:
    order_id: int
    total_amount: float
    created_at: datetime
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Category": [("name",)],
    "Customer": [("email",)],
    "OrderItem": [("order_id", "product_id")],
}


TABLE_NAMES: Dict[str, str] = {
    "OrderItem": "order_items",
}

