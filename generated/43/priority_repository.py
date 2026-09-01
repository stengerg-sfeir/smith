"""PriorityRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Priority


class PriorityRepository:
    """SQLite repository for Priority over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, priority: Priority) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO priorities (name, value) VALUES (?, ?)",
                (priority.name, priority.value),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Priority]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM priorities WHERE id = ?", (id,)
            ).fetchone()
            return Priority(**dict(row)) if row else None

    def get_all(self) -> List[Priority]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM priorities ORDER BY id"
            ).fetchall()
            return [Priority(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, value: Optional[Any] = None) -> List[Priority]:
        with self.db.connect() as conn:
            query = "SELECT * FROM priorities WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if value is not None:
                query += ' AND value = ?'
                params.append(value)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Priority(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'value']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE priorities SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM priorities WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

