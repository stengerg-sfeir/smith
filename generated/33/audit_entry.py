"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AuditRecord:
    customer_id: int
    operation: str
    timestamp: datetime
    id: Optional[int] = None

