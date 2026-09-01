"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Appointment:
    start_time: datetime
    end_time: datetime
    id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None

