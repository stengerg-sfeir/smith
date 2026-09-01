"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Customer:
    name: str
    email: str
    id: Optional[int] = None


@dataclass
class Order:
    customer_id: int
    order_date: datetime
    status: str
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
    "Order": [("customer_id", "order_date")],
}

