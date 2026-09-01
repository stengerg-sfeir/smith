"""Service layer."""
from __future__ import annotations

from typing import List

from booking_repository import BookingRepository
from database import Database
from exceptions import (
    BookingConflictError,
    GuestNotFoundError,
    InvalidDateError,
    RoomNotFoundError,
)
from guest_repository import GuestRepository
from models import Booking, Guest, Room
from room_repository import RoomRepository


class BookingService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.booking_repo = BookingRepository(db)
        self.guest_repo = GuestRepository(db)
        self.room_repo = RoomRepository(db)

    def add_room(self, room_number: str, floor: int, room_type: str, price_per_night: str) -> None:
        room = Room(room_number=room_number, floor=floor, room_type=room_type, price_per_night=price_per_night)
        return self.room_repo.create(room)

    def list_room(self) -> List[Room]:
        return self.room_repo.list()

    def add_guest(self, first_name: str, last_name: str, email: str, phone: str) -> None:
        guest = Guest(first_name=first_name, last_name=last_name, email=email, phone=phone)
        return self.guest_repo.create(guest)

    def book_guest(self, guest_id: int, room_id: int, check_in_date: str, check_out_date: str) -> None:
        """
            Books a guest in a room for a specified date range.
        
            Args:
                guest_id: ID of the guest making the booking
                room_id: ID of the room to book
                check_in_date: Check-in date in 'YYYY-MM-DD' format
                check_out_date: Check-out date in 'YYYY-MM-DD' format
            
            Raises:
                GuestNotFoundError: If guest does not exist
                RoomNotFoundError: If room does not exist
                InvalidDateError: If dates are invalid or check-out date is before check-in date
                BookingConflictError: If booking overlaps with existing bookings for the room
            """
        from datetime import datetime
        try:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d')
            check_out = datetime.strptime(check_out_date, '%Y-%m-%d')
            if check_out <= check_in:
                raise InvalidDateError('Check-out date must be after check-in date')
        except ValueError as e:
            raise InvalidDateError(f'Invalid date format: {str(e)}')
        guest = self.guest_repo.get_by_id(guest_id)
        if not guest:
            raise GuestNotFoundError(f'Guest with ID {guest_id} not found')
        room = self.room_repo.get_by_id(room_id)
        if not room:
            raise RoomNotFoundError(f'Room with ID {room_id} not found')
        overlapping_bookings = self.booking_repo.get_overlapping_bookings_for_room(room_id=room_id, check_in_date=check_in_date, check_out_date=check_out_date)
        if overlapping_bookings:
            for booking in overlapping_bookings:
                if booking.check_in_date < check_out_date and booking.check_out_date > check_in_date:
                    raise BookingConflictError(f'Booking conflict: Room {room_id} is already booked during the period {check_in_date} to {check_out_date}')
        new_booking = Booking(check_in_date=check_in_date, check_out_date=check_out_date, guest_id=guest_id, room_id=room_id, status='confirmed')
        self.booking_repo.create(new_booking)

    def list_booking(self, check_in_date: str, check_out_date: str) -> List[Booking]:
        return self.booking_repo.list(check_in_date=check_in_date, check_out_date=check_out_date)

