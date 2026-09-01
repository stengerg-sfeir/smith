"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Room:
    room_number: str
    floor: int
    room_type: str
    price_per_night: float
    id: Optional[int] = None


@dataclass
class Guest:
    first_name: str
    last_name: str
    email: str
    id: Optional[int] = None
    phone: Optional[str] = None


@dataclass
class Booking:
    room_id: int
    guest_id: int
    check_in_date: date
    check_out_date: date
    status: str
    id: Optional[int] = None


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "Guest": [("email",)],
    "Room": [("room_number",)],
}

