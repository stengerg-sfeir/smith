"""ProjectRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Project, Task


class ProjectRepository:
    """SQLite repository for Project over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, project: Project) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO projects (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project.name, project.description, project.created_at, project.updated_at),
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

    def list(self, name: Optional[Any] = None, description: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, updated_at: Optional[Any] = None, updated_at_end: Optional[Any] = None) -> List[Project]:
        with self.db.connect() as conn:
            query = "SELECT * FROM projects WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
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
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Project(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'created_at', 'updated_at']
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
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM projects WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_project_tasks_with_priority_and_status(self, project_id: int, priority_filter: int, status_filter: str) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM tasks WHERE project_id = ? AND priority = ? AND status = ?', (project_id, priority_filter, status_filter)).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_overdue_tasks(self, project_id: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE project_id = ? AND due_date < datetime('now', 'start of day')", (project_id,)).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_by_status(self, status: str, project_id: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM tasks WHERE project_id = ? AND status = ?', (project_id, status)).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_with_due_date_range(self, project_id: int, start_date: str, end_date: str) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM tasks WHERE project_id = ? AND due_date BETWEEN ? AND ?', (project_id, start_date, end_date)).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_project_task_count_by_status(self, project_id: int) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, COUNT(*) as count FROM tasks WHERE project_id = ? GROUP BY status', (project_id,)).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_project_task_summary(self, project_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute("\n                SELECT \n                    COUNT(*) as total_tasks,\n                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,\n                    COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress_tasks,\n                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_tasks\n                FROM tasks WHERE project_id = ?\n                ", (project_id,)).fetchone()
            return {'total_tasks': rows[0] if rows else 0, 'completed_tasks': rows[1] if rows else 0, 'in_progress_tasks': rows[2] if rows else 0, 'pending_tasks': rows[3] if rows else 0}

    def get_tasks_with_high_priority_due_soon(self, project_id: int, days_threshold: int) -> list[Task]:
        with self.db.connect() as conn:
            threshold_date = f"datetime('now', '{days_threshold} days')"
            rows = conn.execute("\n                SELECT * FROM tasks \n                WHERE project_id = ? \n                AND priority = (SELECT id FROM priorities WHERE value = 1) \n                AND due_date BETWEEN ? AND datetime('now', 'start of day')\n                ", (project_id, threshold_date)).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_project_with_active_tasks(self, project_id: int) -> Project:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
            if row is None:
                raise ValueError(f'Project with id {project_id} not found')
            return Project(**dict(row))

