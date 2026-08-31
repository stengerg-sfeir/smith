"""ReservationRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Reservation, Room


class ReservationRepository:
    """SQLite repository for Reservation over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, reservation: Reservation) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO reservations (customer_id, room_id, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)",
                (reservation.customer_id, reservation.room_id, reservation.start_date, reservation.end_date, reservation.status),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Reservation]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reservations WHERE id = ?", (id,)
            ).fetchone()
            return Reservation(**dict(row)) if row else None

    def get_all(self) -> List[Reservation]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reservations ORDER BY id"
            ).fetchall()
            return [Reservation(**dict(r)) for r in rows]

    def list(self, customer_id: Optional[Any] = None, room_id: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None, status: Optional[Any] = None) -> List[Reservation]:
        with self.db.connect() as conn:
            query = "SELECT * FROM reservations WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if room_id is not None:
                query += ' AND room_id = ?'
                params.append(room_id)
            if start_date is not None:
                query += ' AND start_date >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND end_date <= ?'
                params.append(end_date)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Reservation(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'room_id', 'start_date', 'end_date', 'status']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE reservations SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM reservations WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def create_reservation(self, customer_id: int, room_id: int, start_date: datetime, end_date: datetime, status: str) -> int:
        obj = Reservation(customer_id=customer_id, room_id=room_id, start_date=start_date, end_date=end_date, status=status)
        self.create(obj)
        return obj

    def get_reservation_by_id(self, reservation_id: int) -> Reservation:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,)).fetchall()
            return Reservation(**dict(rows[0])) if rows else None

    def list_reservations_by_customer(self, customer_id: int) -> list[Reservation]:
        return self.list(
            customer_id=customer_id,
        )

    def list_reservations_by_room(self, room_id: int) -> list[Reservation]:
        return self.list(
            room_id=room_id,
        )

    def list_reservations_overlapping_with_date(self, room_id: int, start_date: datetime, end_date: datetime) -> list[Reservation]:
        return self.list(
            room_id=room_id,
            start_date=start_date,
            end_date=end_date,
        )

    def get_reservation_count_by_room(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT room_id, COUNT(*) AS count FROM reservations GROUP BY room_id').fetchall()
            return {str(row[0]): row[1] for row in rows}

    def get_reservations_with_overlaps(self, room_id: int) -> list[Reservation]:
        return self.list(
            room_id=room_id,
        )

    def get_available_rooms_for_date_range(self, start_date: datetime, end_date: datetime) -> list[Room]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_total_reservations_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, COUNT(*) AS count FROM reservations GROUP BY status').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_reservations_with_customer_and_room_details(self, reservation_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT r.id, r.customer_id, r.room_id, r.start_date, r.end_date, r.status,\n                c.name AS customer_name, c.phone AS customer_phone,\n                ro.room_number, ro.room_type, ro.capacity, ro.floor\n                FROM reservations r\n                JOIN customers c ON r.customer_id = c.id\n                JOIN rooms ro ON r.room_id = ro.id\n                WHERE r.id = ?\n            ', (reservation_id,)).fetchall()
            if not rows:
                return {}
            reservation_data = rows[0]
            return {'reservation_id': reservation_data[0], 'customer_id': reservation_data[1], 'room_id': reservation_data[2], 'start_date': reservation_data[3], 'end_date': reservation_data[4], 'status': reservation_data[5], 'customer_name': reservation_data[6], 'customer_phone': reservation_data[7], 'room_number': reservation_data[8], 'room_type': reservation_data[9], 'capacity': reservation_data[10], 'floor': reservation_data[11]}

