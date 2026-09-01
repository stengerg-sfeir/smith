"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Discount:
    name: str
    type: str
    value: float
    id: Optional[int] = None
    min_order_amount: Optional[float] = None
    max_discount_amount: Optional[float] = None

