"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
@dataclass
class Category:
    name: str
    id: Optional[int] = None
    description: Optional[str] = None
    reorder_threshold: Optional[int] = None


@dataclass
class Product:
    sku: str
    name: str
    category_id: int
    price_cents: int
    stock_qty: int
    id: Optional[int] = None
    low_active: Optional[bool] = None

