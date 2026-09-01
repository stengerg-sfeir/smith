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
    id: Optional[int] = None
    description: Optional[str] = None
    category: Optional[str] = None


@dataclass
class Order:
    customer_id: int
    order_date: datetime
    status: str
    total_amount: float
    tax_rate: float
    id: Optional[int] = None
    discount_id: Optional[int] = None


@dataclass
class OrderLine:
    order_id: int
    product_id: int
    quantity: int
    unit_price: float
    line_total: float
    id: Optional[int] = None


@dataclass
class Discount:
    name: str
    type: str
    value: float
    id: Optional[int] = None
    min_order_amount: Optional[float] = None
    max_discount_amount: Optional[float] = None


@dataclass
class Tax:
    name: str
    rate: float
    tax_type: str
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
}

