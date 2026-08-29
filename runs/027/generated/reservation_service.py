"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from customer_repository import CustomerRepository
from database import Database
from models import Reservation, Room
from reservation_repository import ReservationRepository


class ReservationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.reservation_repo = ReservationRepository(db)

    def create_reservation(self, customer_id: int, room_id: int, start_date: datetime, end_date: datetime, status: str) -> int:
        reservation = Reservation(customer_id=customer_id, room_id=room_id, start_date=start_date, end_date=end_date, status=status)
        return self.reservation_repo.create(reservation)

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.reservation_repo.get_by_id(reservation_id)

    def list_reservations_by_customer(self, customer_id: int) -> list[Reservation]:
        return self.reservation_repo.list_reservations_by_customer(customer_id)

    def list_reservations_by_room(self, room_id: int) -> list[Reservation]:
        return self.reservation_repo.list_reservations_by_room(room_id)

    def list_reservations_overlapping_with_date(self, room_id: int, start_date: datetime, end_date: datetime) -> list[Reservation]:
        return self.reservation_repo.list_reservations_overlapping_with_date(room_id, start_date, end_date)

    def get_overlapping_reservations_report(self, room_id: int, start_date: datetime, end_date: datetime) -> list[dict]:
        return self.reservation_repo.get_overlapping_reservations_report(room_id, start_date, end_date)

    def get_total_reservations_by_customer(self) -> dict[int, int]:
        return self.reservation_repo.get_total_reservations_by_customer()

    def get_available_rooms_for_date_range(self, start_date: datetime, end_date: datetime) -> list[Room]:
        return self.reservation_repo.get_available_rooms_for_date_range(start_date, end_date)

