"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Product:
    sku: str
    name: str
    category: str
    price: float
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Product": [("sku", "category")],
}

