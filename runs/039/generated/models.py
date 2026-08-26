"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    email: str
    password_hash: str
    role: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Product:
    name: str
    price: float
    stock_quantity: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Order:
    user_id: int
    status: str
    total_amount: float
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None

