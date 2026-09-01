"""EventRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Event


class EventRepository:
    """SQLite repository for Event over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, event: Event) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO events (title, description, max_participants, current_participants, start_time, end_time, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event.title, event.description, event.max_participants, event.current_participants, event.start_time, event.end_time, event.created_at, event.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Event]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE id = ?", (id,)
            ).fetchone()
            return Event(**dict(row)) if row else None

    def get_all(self) -> List[Event]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id"
            ).fetchall()
            return [Event(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, start_time: Optional[Any] = None, end_time: Optional[Any] = None, max_participants: Optional[Any] = None, current_participants: Optional[Any] = None, description: Optional[Any] = None, max_start_time: Optional[Any] = None) -> List[Event]:
        with self.db.connect() as conn:
            query = "SELECT * FROM events WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if start_time is not None:
                query += ' AND start_time >= ?'
                params.append(start_time)
            if end_time is not None:
                query += ' AND end_time <= ?'
                params.append(end_time)
            if max_participants is not None:
                query += ' AND max_participants = ?'
                params.append(max_participants)
            if current_participants is not None:
                query += ' AND current_participants = ?'
                params.append(current_participants)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if max_start_time is not None:
                query += ' AND start_time <= ?'
                params.append(max_start_time)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Event(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
            query = f"UPDATE events SET {set_clause} WHERE id = ?"
            params = list(data.values()) + [id]
            cur.execute(query, params)
            conn.commit()
            return cur.rowcount > 0
