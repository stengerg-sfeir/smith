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
                "INSERT INTO tasks (project_id, title, description, priority, status, due_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task.project_id, task.title, task.description, task.priority, task.status, task.due_date, task.created_at, task.updated_at),
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

    def list(self, title: Optional[Any] = None, description: Optional[Any] = None, priority: Optional[Any] = None, status: Optional[Any] = None, due_date: Optional[Any] = None, due_date_start: Optional[Any] = None, due_date_end: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, updated_at: Optional[Any] = None, updated_at_end: Optional[Any] = None, project_id: Optional[Any] = None, max_priority: Optional[Any] = None, min_priority: Optional[Any] = None) -> List[Task]:
        with self.db.connect() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if priority is not None:
                query += ' AND priority = ?'
                params.append(priority)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if due_date is not None:
                query += ' AND due_date = ?'
                params.append(due_date)
            if due_date_start is not None:
                query += ' AND due_date >= ?'
                params.append(due_date_start)
            if due_date_end is not None:
                query += ' AND due_date <= ?'
                params.append(due_date_end)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            if updated_at is not None:
                query += ' AND updated_at >= ?'
                params.append(updated_at)
            if updated_at_end is not None:
                query += ' AND updated_at <= ?'
                params.append(updated_at_end)
            if project_id is not None:
                query += ' AND project_id = ?'
                params.append(project_id)
            if max_priority is not None:
                query += ' AND priority <= ?'
                params.append(max_priority)
            if min_priority is not None:
                query += ' AND priority >= ?'
                params.append(min_priority)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['project_id', 'title', 'description', 'priority', 'status', 'due_date', 'created_at', 'updated_at']
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

    def get_tasks_by_priority_and_status(self, priority: int, status: str) -> list[Task]:
        return self.list(
            priority=priority,
            status=status,
        )

    def get_tasks_with_pending_due_dates(self, project_id: int) -> list[Task]:
        return self.list(
            project_id=project_id,
        )

    def get_tasks_with_status_and_priority_range(self, status: str, min_priority: int, max_priority: int) -> list[Task]:
        return self.list(
            status=status,
            min_priority=min_priority,
            max_priority=max_priority,
        )

    def get_tasks_by_project_and_due_date_range(self, project_id: int, start_date: date, end_date: date) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM tasks r JOIN projects o ON r.project_id = o.id WHERE o.name = ? AND r.due_date >= ? AND r.due_date <= ?",
                (project_id, start_date, end_date)
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_with_high_priority_and_overdue(self, project_id: int, days_threshold: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM tasks r JOIN projects o ON r.project_id = o.id WHERE o.id = ?",
                (project_id,)
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_count_by_priority(self, project_id: int) -> dict[int, int]:
        return self.list(
            project_id=project_id,
        )

    def get_project_task_overview(self, project_id: int) -> dict:
        return self.list(
            project_id=project_id,
        )

