"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class StockRecord:
    product_id: int
    stock_quantity: int
    last_updated: datetime
    id: Optional[int] = None

