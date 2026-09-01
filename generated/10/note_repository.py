"""NoteRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Note


class NoteRepository:
    """SQLite repository for Note over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, note: Note) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO notes (title, content, created_at) VALUES (?, ?, ?)",
                (note.title, note.content, note.created_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Note]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (id,)
            ).fetchone()
            return Note(**dict(row)) if row else None

    def get_all(self) -> List[Note]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY id"
            ).fetchall()
            return [Note(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, created_after: Optional[Any] = None, created_before: Optional[Any] = None, content: Optional[Any] = None) -> List[Note]:
        with self.db.connect() as conn:
            query = "SELECT * FROM notes WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if created_after is not None:
                query += ' AND created_at >= ?'
                params.append(created_after)
            if created_before is not None:
                query += ' AND created_at <= ?'
                params.append(created_before)
            if content is not None:
                query += ' AND content = ?'
                params.append(content)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Note(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'content', 'created_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE notes SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM notes WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_notes_by_title(self, title: str) -> list[Note]:
        return self.list(
            title=title,
        )

    def get_notes_by_created_date_range(self, start_date: datetime, end_date: datetime) -> list[Note]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notes WHERE created_at >= ? AND created_at <= ?", ((start_date, end_date))
            ).fetchall()
            return [Note(**dict(r)) for r in rows]

    def get_note_count_by_month(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT substr(created_at, 1, 7) AS k, COUNT(*) AS n FROM notes GROUP BY k"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def search_notes_by_content(self, query: str) -> list[Note]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notes WHERE (title LIKE ? OR content LIKE ?)",
                ("%" + query + "%", "%" + query + "%")
            ).fetchall()
            return [Note(**dict(r)) for r in rows]

    def get_notes_with_latest_update(self) -> list[Note]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY created_at DESC"
            ).fetchall()
            return [Note(**dict(r)) for r in rows]

