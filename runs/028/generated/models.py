"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Invoice:
    customer_id: int
    total_amount: float
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class InvoiceLine:
    invoice_id: int
    product_id: int
    quantity: int
    unit_price: float
    id: Optional[int] = None


@dataclass
class Customer:
    name: str
    email: str
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class Product:
    name: str
    price: float
    id: Optional[int] = None
    description: Optional[str] = None

