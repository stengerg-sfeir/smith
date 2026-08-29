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
            row = conn.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,)).fetchone()
            if row is None:
                raise ValueError(f'Reservation with id {reservation_id} not found')
            return Reservation(**dict(row))

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
            rows = conn.execute('\n                SELECT r.room_id, COUNT(*) AS count\n                FROM reservations r\n                GROUP BY r.room_id\n            ').fetchall()
            result: Dict[str, int] = {}
            for row in rows:
                room_id = row[0]
                count = row[1]
                result[str(room_id)] = count
            return result

    def get_reservations_by_status(self, status: str) -> list[Reservation]:
        return self.list(
            status=status,
        )

    def get_available_rooms_for_date_range(self, start_date: datetime, end_date: datetime) -> list[Room]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_total_reservations_by_customer(self) -> dict[int, int]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT r.customer_id, COUNT(*) AS count\n                FROM reservations r\n                GROUP BY r.customer_id\n            ').fetchall()
            result: Dict[int, int] = {}
            for row in rows:
                customer_id = row[0]
                count = row[1]
                result[customer_id] = count
            return result

    def get_overlapping_reservations_report(self, room_id: int, start_date: datetime, end_date: datetime) -> list[dict]:
        return self.list(
            room_id=room_id,
            start_date=start_date,
            end_date=end_date,
        )

