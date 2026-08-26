"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    status: str
    created_at: datetime
    updated_at: datetime
    total_amount: float
    id: Optional[int] = None
    customer_id: Optional[int] = None

