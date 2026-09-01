"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderLine:
    order_id: int
    product_id: int
    quantity: int
    unit_price: float
    line_total: float
    id: Optional[int] = None

