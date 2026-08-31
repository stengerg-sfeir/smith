"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Customer:
    name: str
    email: str
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class Room:
    room_number: str
    floor: int
    capacity: int
    room_type: str
    id: Optional[int] = None


@dataclass
class Reservation:
    customer_id: int
    room_id: int
    start_date: datetime
    end_date: datetime
    status: str
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Customer": [("email",)],
    "Room": [("room_number",)],
}

