"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    customer_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    total_amount: float
    id: Optional[int] = None


@dataclass
class Notification:
    order_id: int
    message: str
    sent_at: datetime
    sent_to: str
    id: Optional[int] = None

