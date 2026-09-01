"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Client:
    name: str
    email: str
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class Invoice:
    client_id: int
    invoice_number: str
    due_date: date
    amount: float
    status: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Payment:
    invoice_id: int
    amount: float
    payment_date: date
    status: str
    created_at: datetime
    id: Optional[int] = None
    method: Optional[str] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Invoice": [("invoice_number",)],
}

