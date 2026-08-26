"""TaskRepository data access."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from models import Task


class TaskRepository:
    """SQLite repository for Task over the shared Database."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def create(self, task: Task) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tasks (title, description, status, priority, due_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task.title, task.description, task.status, task.priority, task.due_date, task.created_at, task.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Task]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (id,)
            ).fetchone()
            return Task(**dict(row)) if row else None

    def get_all(self) -> List[Task]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY id"
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, status: Optional[Any] = None, priority: Optional[Any] = None, due_date: Optional[Any] = None) -> List[Task]:
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if priority is not None:
                query += ' AND priority >= ?'
                params.append(priority)
            if due_date is not None:
                query += ' AND due_date >= ?'
                params.append(due_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'description', 'status', 'priority', 'due_date', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tasks SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                return False
            return True

    def delete(self, id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM tasks WHERE id = ?", (id,))
            conn.commit()
            return cur.rowcount > 0
