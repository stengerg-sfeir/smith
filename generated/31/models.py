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
class Account:
    customer_id: int
    balance: float
    created_at: datetime
    id: Optional[int] = None


@dataclass
class Deposit:
    account_id: int
    amount: float
    created_at: datetime
    id: Optional[int] = None


@dataclass
class Withdrawal:
    account_id: int
    amount: float
    created_at: datetime
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
}

