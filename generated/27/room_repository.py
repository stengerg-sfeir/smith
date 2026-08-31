"""RoomRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Reservation, Room


class RoomRepository:
    """SQLite repository for Room over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, room: Room) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO rooms (room_number, floor, capacity, room_type) VALUES (?, ?, ?, ?)",
                (room.room_number, room.floor, room.capacity, room.room_type),
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

    def list(self, room_number: Optional[Any] = None, floor: Optional[Any] = None, room_type: Optional[Any] = None, min_capacity: Optional[Any] = None) -> List[Room]:
        with self.db.connect() as conn:
            query = "SELECT * FROM rooms WHERE 1=1"
            params: List[Any] = []
            if room_number is not None:
                query += ' AND room_number = ?'
                params.append(room_number)
            if floor is not None:
                query += ' AND floor = ?'
                params.append(floor)
            if room_type is not None:
                query += ' AND room_type = ?'
                params.append(room_type)
            if min_capacity is not None:
                query += ' AND capacity >= ?'
                params.append(min_capacity)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Room(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['room_number', 'floor', 'capacity', 'room_type']
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
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM rooms WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_room_by_id(self, room_id: int) -> Optional[Room]:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
            return Room(**dict(row)) if row else None

    def list_rooms_by_floor(self, floor: int) -> list[Room]:
        return self.list(
            floor=floor,
        )

    def list_rooms_by_type(self, room_type: str) -> list[Room]:
        return self.list(
            room_type=room_type,
        )

    def get_available_room_count_by_floor(self, floor: int) -> int:
        return self.list(
            floor=floor,
        )

    def get_rooms_with_capacity_above(self, min_capacity: int) -> list[Room]:
        return self.list(
            min_capacity=min_capacity,
        )

    def get_rooms_with_overlapping_reservations(self, room_id: int, start_date: str, end_date: str) -> list[Reservation]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT r.* FROM reservations r \n                   WHERE r.room_id = ? \n                   AND r.start_date < ? \n                   AND r.end_date > ?', (room_id, end_date, start_date)).fetchall()
            return [Reservation(**dict(r)) for r in rows]

    def get_rooms_with_active_reservations(self) -> list[Room]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT r.*, rooms.* FROM reservations r \n                   JOIN rooms ON r.room_id = rooms.id \n                   WHERE r.status = 'active'").fetchall()
            return [Room(**dict(r)) for r in rows]

    def get_rooms_by_room_number_pattern(self, pattern: str) -> list[Room]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rooms WHERE (room_number LIKE ? OR room_type LIKE ?)",
                ("%" + pattern + "%", "%" + pattern + "%")
            ).fetchall()
            return [Room(**dict(r)) for r in rows]

