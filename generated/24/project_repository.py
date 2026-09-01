"""ProjectRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import ProjectNotFoundError
from models import Project, Task


class ProjectRepository:
    """SQLite repository for Project over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, project: Project) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO projects (title, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project.title, project.description, project.created_at, project.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Project]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (id,)
            ).fetchone()
            return Project(**dict(row)) if row else None

    def get_all(self) -> List[Project]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY id"
            ).fetchall()
            return [Project(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, description: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None) -> List[Project]:
        with self.db.connect() as conn:
            query = "SELECT * FROM projects WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Project(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'description', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE projects SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ProjectNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM projects WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_project_tasks_by_status_and_priority(self, status: str, priority: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM tasks WHERE status = ? AND priority = ?', (status, priority)).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_project_tasks_with_filter(self, title: Optional[str]=None, status: Optional[str]=None, priority: Optional[int]=None, project_id: Optional[int]=None) -> list[Task]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM tasks WHERE 1=1'
            params = []
            if title is not None:
                query += ' AND title LIKE ?'
                params.append(f'%{title}%')
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if priority is not None:
                query += ' AND priority = ?'
                params.append(priority)
            if project_id is not None:
                query += ' AND project_id = ?'
                params.append(project_id)
            rows = conn.execute(query, params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_project_task_count_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT project_id AS k, COUNT(*) AS n FROM tasks GROUP BY project_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_project_task_completion_rate(self) -> float:
        with self.db.connect() as conn:
            total_tasks_query = 'SELECT COUNT(*) FROM tasks'
            completed_tasks_query = "SELECT COUNT(*) FROM tasks WHERE status = 'completed'"
            total_tasks_result = conn.execute(total_tasks_query).fetchone()
            completed_tasks_result = conn.execute(completed_tasks_query).fetchone()
            total_tasks = total_tasks_result[0] if total_tasks_result[0] is not None else 0
            completed_tasks = completed_tasks_result[0] if completed_tasks_result[0] is not None else 0
            if total_tasks == 0:
                return 0.0
            return completed_tasks / total_tasks

    def get_project_tasks_overdue(self) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM tasks').fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_project_task_summary(self) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    status, \n                    priority, \n                    COUNT(*) as count\n                FROM tasks \n                GROUP BY status, priority\n            '
            rows = conn.execute(query).fetchall()
            summary = {}
            for row in rows:
                status = row[0]
                priority = row[1]
                count = row[2]
                summary[status, priority] = count
            return summary

