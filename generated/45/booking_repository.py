"""BookingRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Booking, Room


class BookingRepository:
    """SQLite repository for Booking over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, booking: Booking) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO bookings (room_id, guest_id, check_in_date, check_out_date, status) VALUES (?, ?, ?, ?, ?)",
                (booking.room_id, booking.guest_id, booking.check_in_date, booking.check_out_date, booking.status),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Booking]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE id = ?", (id,)
            ).fetchone()
            return Booking(**dict(row)) if row else None

    def get_all(self) -> List[Booking]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM bookings ORDER BY id"
            ).fetchall()
            return [Booking(**dict(r)) for r in rows]

    def list(self, check_in_date: Optional[Any] = None, check_out_date: Optional[Any] = None, guest_id: Optional[Any] = None, room_id: Optional[Any] = None, status: Optional[Any] = None) -> List[Booking]:
        with self.db.connect() as conn:
            query = "SELECT * FROM bookings WHERE 1=1"
            params: List[Any] = []
            if check_in_date is not None:
                query += ' AND check_in_date >= ?'
                params.append(check_in_date)
            if check_out_date is not None:
                query += ' AND check_out_date >= ?'
                params.append(check_out_date)
            if guest_id is not None:
                query += ' AND guest_id = ?'
                params.append(guest_id)
            if room_id is not None:
                query += ' AND room_id = ?'
                params.append(room_id)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Booking(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['room_id', 'guest_id', 'check_in_date', 'check_out_date', 'status']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE bookings SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM bookings WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_bookings_by_date_range(self, check_in_date: date, check_out_date: date) -> list[Booking]:
        return self.list(
            check_in_date=check_in_date,
            check_out_date=check_out_date,
        )

    def get_bookings_by_room_id(self, room_id: int) -> list[Booking]:
        return self.list(
            room_id=room_id,
        )

    def get_bookings_by_guest_id(self, guest_id: int) -> list[Booking]:
        return self.list(
            guest_id=guest_id,
        )

    def get_bookings_with_conflict(self, check_in_date: date, check_out_date: date, room_id: int) -> list[Booking]:
        return self.list(
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            room_id=room_id,
        )

    def get_booking_summary_by_room_type(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT room_type, COUNT(*) AS count FROM bookings JOIN rooms ON bookings.room_id = rooms.id GROUP BY room_type').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_total_bookings_in_period(self, check_in_date: str, check_out_date: str) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM bookings WHERE check_in_date BETWEEN ? AND ?', (check_in_date, check_out_date)).fetchone()
            return rows[0] if rows else 0

    def get_bookings_with_status(self, status: str) -> list[Booking]:
        return self.list(
            status=status,
        )

    def get_rooms_with_bookings_in_period(self, check_in_date: date, check_out_date: date) -> list[Room]:
        return self.list(
            check_in_date=check_in_date,
            check_out_date=check_out_date,
        )

    def get_overlapping_bookings_for_room(self, room_id: int, check_in_date: date, check_out_date: date) -> list[Booking]:
        return self.list(
            room_id=room_id,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
        )

    def get_booking_count_by_floor(self) -> dict[int, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT floor, COUNT(*) AS count FROM bookings JOIN rooms ON bookings.room_id = rooms.id GROUP BY floor').fetchall()
            return {row[0]: row[1] for row in rows}

