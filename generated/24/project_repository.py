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

    def list(self, description: Optional[Any] = None, title: Optional[Any] = None) -> List[Project]:
        with self.db.connect() as conn:
            query = "SELECT * FROM projects WHERE 1=1"
            params: List[Any] = []
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
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

    def get_project_tasks_summary(self, project_id: int, status_filter: str, priority_filter: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) as task_count, status, priority FROM tasks WHERE project_id = ? AND status = ? AND priority = ? GROUP BY status, priority', (project_id, status_filter, priority_filter)).fetchall()
            return {row[1]: row[0] for row in rows}

    def list_projects_with_task_count(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT id, title, description, created_at, updated_at FROM projects').fetchall()
            return [Project(**dict(r)) for r in rows]

    def get_project_with_tasks(self, project_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT id, title, description, created_at, updated_at FROM projects WHERE id = ?', (project_id,)).fetchone()
            if not rows:
                raise ProjectNotFoundError(f'Project with id {project_id} not found')
            return Project(**dict(rows))

    def get_task_stats_by_project(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT p.id, p.title, COUNT(t.id) as task_count, SUM(CASE WHEN t.status = "completed" THEN 1 ELSE 0 END) as completed_count, SUM(CASE WHEN t.status = "in_progress" THEN 1 ELSE 0 END) as in_progress_count, SUM(CASE WHEN t.status = "pending" THEN 1 ELSE 0 END) as pending_count FROM projects p LEFT JOIN tasks t ON p.id = t.project_id GROUP BY p.id, p.title').fetchall()
            return {row[1]: {'task_count': row[2], 'completed_count': row[3], 'in_progress_count': row[4], 'pending_count': row[5]} for row in rows}

    def search_tasks_by_title(self, query: str, project_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT id, title, description, priority, status, created_at, updated_at FROM tasks WHERE project_id = ? AND title LIKE ?', (project_id, f'%{query}%')).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_project_completion_rate(self, project_id: int) -> float:
        with self.db.connect() as conn:
            total_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE project_id = ?', (project_id,)).fetchone()[0]
            if total_tasks == 0:
                return 0.0
            completed_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status = "completed"', (project_id,)).fetchone()[0]
            return completed_tasks / total_tasks

    def list_tasks_by_status_and_priority(self, status: str, priority: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT id, title, description, priority, status, created_at, updated_at FROM tasks WHERE status = ? AND priority = ?', (status, priority)).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_total_tasks_by_status(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, COUNT(*) as count FROM tasks GROUP BY status').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_project_task_distribution(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT p.id, p.title, COUNT(t.id) as task_count FROM projects p LEFT JOIN tasks t ON p.id = t.project_id GROUP BY p.id, p.title').fetchall()
            return {row[1]: row[2] for row in rows}

