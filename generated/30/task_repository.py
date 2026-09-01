"""TaskRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Task


class TaskRepository:
    """SQLite repository for Task over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, task: Task) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tasks (title, description, status, priority, due_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task.title, task.description, task.status, task.priority, task.due_date, task.created_at, task.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Task]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (id,)
            ).fetchone()
            return Task(**dict(row)) if row else None

    def get_all(self) -> List[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY id"
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, status: Optional[Any] = None, priority: Optional[Any] = None, due_date: Optional[Any] = None, description: Optional[Any] = None) -> List[Task]:
        with self.db.connect() as conn:
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
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'description', 'status', 'priority', 'due_date', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
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
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM tasks WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_tasks_by_status_and_priority(self, status: str, priority: int) -> list[Task]:
        return self.list(
            status=status,
            priority=priority,
        )

    def get_tasks_with_due_date_range(self, start_date: date, end_date: date) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE due_date >= ? AND due_date <= ?", ((start_date, end_date))
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_task_count_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status AS k, COUNT(*) AS n FROM tasks GROUP BY status"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_overdue_tasks(self) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE due_date IS NOT NULL AND due_date < date('now')"
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_with_pagination(self, page: int, page_size: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size)
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def search_tasks_by_title(self, query: str) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE (title LIKE ? OR description LIKE ? OR status LIKE ?)",
                ("%" + query + "%", "%" + query + "%", "%" + query + "%")
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_with_status_and_created_date_range(self, status: str, start_date: date, end_date: date) -> list[Task]:
        return []

