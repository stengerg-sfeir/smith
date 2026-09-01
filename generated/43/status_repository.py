"""StatusRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Status


class StatusRepository:
    """SQLite repository for Status over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, status: Status) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO statuses (name) VALUES (?)",
                (status.name),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Status]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM statuses WHERE id = ?", (id,)
            ).fetchone()
            return Status(**dict(row)) if row else None

    def get_all(self) -> List[Status]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM statuses ORDER BY id"
            ).fetchall()
            return [Status(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, max_priority: Optional[Any] = None, min_priority: Optional[Any] = None) -> List[Status]:
        with self.db.connect() as conn:
            query = "SELECT * FROM statuses WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if max_priority is not None:
                query += ' AND id <= ?'
                params.append(max_priority)
            if min_priority is not None:
                query += ' AND id >= ?'
                params.append(min_priority)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Status(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE statuses SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM statuses WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

