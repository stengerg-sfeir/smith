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
class Purchase:
    customer_id: int
    amount: float
    purchase_date: datetime
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
}

