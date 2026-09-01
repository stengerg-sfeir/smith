"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Customer:
    first_name: str
    last_name: str
    email: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    phone: Optional[str] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
}

