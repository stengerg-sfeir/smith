"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Contact:
    name: str
    id: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None

