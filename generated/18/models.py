"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Contact:
    first_name: str
    last_name: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Contact": [("email",)],
}

