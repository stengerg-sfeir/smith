"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
class OrderCancellation:
    order_id: int
    cancellation_date: datetime
    id: Optional[int] = None
    reason: Optional[str] = None
    canceled_by: Optional[str] = None


@dataclass
class StockRestoration:
    order_id: int
    product_id: int
    restored_quantity: int
    restoration_date: datetime
    id: Optional[int] = None

