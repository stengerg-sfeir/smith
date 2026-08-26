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
                "INSERT INTO tasks (title, description, status, priority, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task.title, task.description, task.status, task.priority, task.project_id, task.created_at, task.updated_at),
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

    def list(self, title: Optional[Any] = None, status: Optional[Any] = None, priority: Optional[Any] = None, created_at: Optional[Any] = None, description: Optional[Any] = None, project_id: Optional[Any] = None) -> List[Task]:
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
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if project_id is not None:
                query += ' AND project_id = ?'
                params.append(project_id)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'description', 'status', 'priority', 'project_id', 'created_at', 'updated_at']
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

    def get_tasks_by_project_and_status(self, project_id: int, status: str) -> list[dict]:
        return self.list(
            project_id=project_id,
            status=status,
        )

    def get_tasks_by_priority_range(self, min_priority: int, max_priority: int) -> list[dict]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks WHERE priority BETWEEN ? AND ?', (min_priority, max_priority))
            rows = cursor.fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_with_project_title(self, project_title: str) -> list[dict]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT t.* FROM tasks t JOIN projects p ON t.project_id = p.id WHERE p.title = ?', (project_title,))
            rows = cursor.fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_task_count_by_status_and_priority(self) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT status, priority, COUNT(*) AS count FROM tasks GROUP BY status, priority')
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                status, priority, count = row
                key = (status, priority)
                result[key] = count
            return result

    def search_tasks_by_title_and_project(self, query: str, project_id: int) -> list[dict]:
        return self.list(
            project_id=project_id,
        )

    def get_tasks_with_completion_rate(self, project_id: int) -> dict:
        return self.list(
            project_id=project_id,
        )

    def get_tasks_by_status_and_priority_with_project_info(self, status: str, priority: int) -> list[dict]:
        return self.list(
            status=status,
            priority=priority,
        )

