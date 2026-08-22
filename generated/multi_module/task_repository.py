"""TaskRepository data access."""
from __future__ import annotations

from datetime import datetime
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
                "INSERT INTO tasks (title, description, status, created_at) VALUES (?, ?, ?, ?)",
                (task.title, task.description, task.status, task.created_at),
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

    def list(self, status: Optional[Any] = None, description: Optional[Any] = None, title: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Task]:
        with self.db.connect() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params: List[Any] = []
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if start_date is not None:
                query += ' AND created_at >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND created_at <= ?'
                params.append(end_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'description', 'status', 'created_at']
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

    def find_by_status(self, status: str) -> List[Task]:
        return self.list(
            status=status,
        )

    def count_tasks_by_status(self, status: str) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)
            )
            return cur.fetchone()[0]

    def get_tasks_with_creation_stats(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT 
                    status,
                    COUNT(*) as task_count,
                    MIN(created_at) as first_created,
                    MAX(created_at) as last_created,
                    AVG(julianday(created_at)) as avg_created_date
                FROM tasks 
                GROUP BY status
                ORDER BY status
                """
            )
            result = {}
            for row in cur.fetchall():
                result[row[0]] = {
                    "task_count": row[1],
                    "first_created": row[2],
                    "last_created": row[3],
                    "avg_created_date": row[4]
                }
            return result

    def get_tasks_in_time_range(self, start_date: datetime, end_date: datetime) -> List[Task]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_tasks_with_status_distribution(self) -> Dict[str, int]:
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
            )
            result = {}
            for row in cur.fetchall():
                result[row[0]] = row[1]
            return result

