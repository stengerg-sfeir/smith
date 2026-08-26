"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Customer:
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class Order:
    customer_id: int
    order_date: datetime
    total_amount: float
    status: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None

