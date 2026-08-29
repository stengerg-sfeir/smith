"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    name: str
    price: float
    quantity: int
    id: Optional[int] = None
    description: Optional[str] = None

