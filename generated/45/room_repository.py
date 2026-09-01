"""RoomRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import RoomNotFoundError
from models import Room


class RoomRepository:
    """SQLite repository for Room over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, room: Room) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO rooms (room_number, floor, room_type, price_per_night) VALUES (?, ?, ?, ?)",
                (room.room_number, room.floor, room.room_type, room.price_per_night),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Room]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rooms WHERE id = ?", (id,)
            ).fetchone()
            return Room(**dict(row)) if row else None

    def get_all(self) -> List[Room]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rooms ORDER BY id"
            ).fetchall()
            return [Room(**dict(r)) for r in rows]

    def list(self, floor: Optional[Any] = None, price_per_night: Optional[Any] = None, room_number: Optional[Any] = None, room_type: Optional[Any] = None) -> List[Room]:
        with self.db.connect() as conn:
            query = "SELECT * FROM rooms WHERE 1=1"
            params: List[Any] = []
            if floor is not None:
                query += ' AND floor = ?'
                params.append(floor)
            if price_per_night is not None:
                query += ' AND price_per_night = ?'
                params.append(price_per_night)
            if room_number is not None:
                query += ' AND room_number = ?'
                params.append(room_number)
            if room_type is not None:
                query += ' AND room_type = ?'
                params.append(room_type)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Room(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['room_number', 'floor', 'room_type', 'price_per_night']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE rooms SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise RoomNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM rooms WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_available_rooms_for_period(self, check_in_date: str, check_out_date: str) -> list[Room]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT DISTINCT r.id, r.room_number, r.room_type, r.floor, r.price_per_night \n                   FROM rooms r \n                   LEFT JOIN bookings b ON r.id = b.room_id \n                   WHERE b.id IS NULL \n                   OR (b.check_in_date >= ? OR b.check_out_date <= ?)\n                   AND b.check_in_date < ? \n                   AND b.check_out_date > ?', (check_in_date, check_out_date, check_in_date, check_out_date)).fetchall()
            return [Room(**dict(r)) for r in rows]

    def get_rooms_by_floor(self, floor: int) -> list[Room]:
        return self.list(
            floor=floor,
        )

    def get_rooms_by_type(self, room_type: str) -> list[Room]:
        return self.list(
            room_type=room_type,
        )

    def get_total_bookings_for_room(self, room_id: int, check_in_date: str, check_out_date: str) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) \n                   FROM bookings \n                   WHERE room_id = ? \n                   AND check_in_date < ? \n                   AND check_out_date > ?', (room_id, check_out_date, check_in_date)).fetchone()
            return rows[0] if rows else 0

    def get_booking_summary_by_floor(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT room_id AS k, COUNT(*) AS n FROM bookings GROUP BY room_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_rooms_with_pending_bookings(self) -> list[Room]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT r.id, r.room_number, r.room_type, r.floor, r.price_per_night \n                   FROM rooms r \n                   JOIN bookings b ON r.id = b.room_id \n                   WHERE b.status = 'pending'").fetchall()
            return [Room(**dict(r)) for r in rows]

    def get_rooms_with_no_bookings(self) -> list[Room]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT r.id, r.room_number, r.room_type, r.floor, r.price_per_night \n                   FROM rooms r \n                   LEFT JOIN bookings b ON r.id = b.room_id \n                   WHERE b.id IS NULL').fetchall()
            return [Room(**dict(r)) for r in rows]

