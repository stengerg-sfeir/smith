"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Event:
    title: str
    max_participants: int
    current_participants: int
    start_time: datetime
    end_time: datetime
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Registration:
    event_id: int
    person_id: int
    created_at: datetime
    id: Optional[int] = None

