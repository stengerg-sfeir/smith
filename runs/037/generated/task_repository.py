"""TaskRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import TaskNotFoundError
from models import Task


class TaskRepository:
    """SQLite repository for Task over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, task: Task) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tasks (project_id, title, description, status, priority, due_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task.project_id, task.title, task.description, task.status, task.priority, task.due_date, task.created_at, task.updated_at),
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

    def list(self, project_id: Optional[Any] = None, status: Optional[Any] = None, priority: Optional[Any] = None, due_date: Optional[Any] = None, due_date_end: Optional[Any] = None, description: Optional[Any] = None, title: Optional[Any] = None) -> List[Task]:
        with self.db.connect() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params: List[Any] = []
            if project_id is not None:
                query += ' AND project_id = ?'
                params.append(project_id)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if priority is not None:
                query += ' AND priority = ?'
                params.append(priority)
            if due_date is not None:
                query += ' AND due_date >= ?'
                params.append(due_date)
            if due_date_end is not None:
                query += ' AND due_date <= ?'
                params.append(due_date_end)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['project_id', 'title', 'description', 'status', 'priority', 'due_date', 'created_at', 'updated_at']
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
                raise TaskNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM tasks WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def create_task(self, project_id: int, title: str, description: Optional[str] = None, status: str = None, priority: int = None, due_date: Optional[date] = None) -> Task:
        raise NotImplementedError()

    def update_task(self, task_id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None, priority: Optional[int] = None, due_date: Optional[date] = None) -> Task:
        raise NotImplementedError()

    def delete_task(self, task_id: int) -> bool:
        raise NotImplementedError()

    def get_task_by_id(self, task_id: int) -> Task:
        raise NotImplementedError()

    def list_tasks_by_project(self, project_id: int, status_filter: Optional[str] = None, priority_filter: Optional[int] = None, due_date_range: Optional[tuple[datetime, datetime]] = None) -> list[Task]:
        return self.list(
            project_id=project_id,
        )

    def get_task_stats_by_status(self) -> dict[str, int]:
        raise NotImplementedError()

    def get_task_completion_rate(self, project_id: int) -> float:
        raise NotImplementedError()

    def get_tasks_with_overdue_due_dates(self) -> list[Task]:
        raise NotImplementedError()

    def get_tasks_by_priority_and_status(self, status: str, priority: int) -> list[Task]:
        return self.list(
            status=status,
            priority=priority,
        )

    def get_project_task_count(self, project_id: int) -> int:
        raise NotImplementedError()

    def search_tasks_by_title(self, query: str, limit: int) -> list[Task]:
        raise NotImplementedError()

