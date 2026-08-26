"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Order:
    created_at: datetime
    updated_at: datetime
    status: str
    id: Optional[int] = None


@dataclass
class OrderLine:
    order_id: int
    product_id: int
    quantity: int
    unit_price: float
    total_price: float
    id: Optional[int] = None


TABLE_NAMES: Dict[str, str] = {
    "OrderLine": "order_lines",
}

