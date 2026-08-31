"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import NotFoundError
from models import Customer, Reservation
from reservation_repository import ReservationRepository
from room_repository import RoomRepository


class ReservationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.room_repo = RoomRepository(db)

    def add_reservation(self, customer_id: int, room_id: int, status: str) -> int:
        reservation = Reservation(customer_id=customer_id, room_id=room_id, status=status, end_date=datetime.datetime.now().isoformat(), start_date=datetime.datetime.now().isoformat())
        return self.reservation_repo.create(reservation)

    def list_reservation(self, customer_id: Optional[int] = None, room_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        results = {}
        for row in self.reservation_repo.list(customer_id=customer_id, room_id=room_id, start_date=start_date, end_date=end_date, status=status):
            key = (row.customer_id, row.room_id)
            results[key] = results.get(key, 0) + row.id
        return results

    def update_reservation(self, id: int, customer_id: Optional[int] = None, room_id: Optional[int] = None, status: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'customer_id': customer_id, 'room_id': room_id, 'status': status}.items() if v is not None}
        return self.reservation_repo.update(id, data)

    def delete_reservation(self, id: int) -> bool:
        return self.reservation_repo.delete(id)

    def check_reservation(self, id: int) -> dict:
        """Check if a reservation exists and return its details with customer and room information."""
        reservation = self.reservation_repo.get_by_id(id)
        if not reservation:
            raise NotFoundError(f'Reservation with id {id} not found')
        reservation_details = self.reservation_repo.get_reservations_with_customer_and_room_details(reservation.id)
        return {'reservation_id': reservation_details['reservation_id'], 'customer_id': reservation_details['customer_id'], 'customer_name': reservation_details['customer_name'], 'customer_phone': reservation_details['customer_phone'], 'room_id': reservation_details['room_id'], 'room_number': reservation_details['room_number'], 'floor': reservation_details['floor'], 'room_type': reservation_details['room_type'], 'capacity': reservation_details['capacity'], 'start_date': reservation_details['start_date'], 'end_date': reservation_details['end_date'], 'status': reservation_details['status']}

    def add_customer(self, name: str, email: str, phone: Optional[str] = None) -> int:
        customer = Customer(name=name, email=email, phone=phone)
        return self.customer_repo.create(customer)

    def add_room(self, room_number: str, floor: int, capacity: int, room_type: str) -> int:
        results = {}
        for row in self.room_repo.list(room_number=room_number, floor=floor, capacity=capacity, room_type=room_type):
            key = row.room_type
            results[key] = results.get(key, 0) + row.id
        return results

