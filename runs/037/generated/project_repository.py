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

    def list(self, description: Optional[Any] = None, name: Optional[Any] = None) -> List[Project]:
        with self.db.connect() as conn:
            query = "SELECT * FROM projects WHERE 1=1"
            params: List[Any] = []
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
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

    def get_project_with_tasks(self, project_id: int) -> ProjectWithTasks:
        return None

    def list_projects_with_task_count(self, status_filter: str, priority_filter: int, due_date_range: tuple[datetime, datetime]) -> list[ProjectWithTaskCount]:
        return []

    def get_project_tasks_summary(self, project_id: int) -> dict[str, int]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    status, \n                    COUNT(*) as count\n                FROM tasks \n                WHERE project_id = ?\n                GROUP BY status\n            '
            rows = conn.execute(query, (project_id,)).fetchall()
            result = {}
            for row in rows:
                result[row[0]] = row[1]
            return result

    def get_overdue_tasks_count_by_project(self) -> dict[int, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT project_id AS k, COUNT(*) AS n FROM tasks GROUP BY project_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_project_completion_rate(self, project_id: int) -> float:
        with self.db.connect() as conn:
            query = "\n                SELECT \n                    COUNT(*) as completed_count,\n                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as total_completed\n                FROM tasks \n                WHERE project_id = ?\n            "
            row = conn.execute(query, (project_id,)).fetchone()
            if row is None:
                return 0.0
            total_tasks = row[0]
            completed_tasks = row[1]
            if total_tasks == 0:
                return 0.0
            return completed_tasks / total_tasks

    def search_projects_by_name(self, query: str, limit: int) -> list[Project]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE (name LIKE ? OR description LIKE ?) LIMIT ?",
                ("%" + query + "%", "%" + query + "%", limit)
            ).fetchall()
            return [Project(**dict(r)) for r in rows]

    def get_tasks_by_status_and_priority(self, status: str, priority: int) -> list[Task]:
        with self.db.connect() as conn:
            query = '\n                SELECT id, title, description, due_date, priority, status, created_at, updated_at\n                FROM tasks \n                WHERE status = ? AND priority = ?\n            '
            rows = conn.execute(query, (status, priority)).fetchall()
            return [Task(id=row[0], title=row[1], description=row[2], due_date=row[3], priority=row[4], status=row[5], created_at=row[6], updated_at=row[7]) for row in rows]

    def get_project_creation_trend(self, start_date: datetime, end_date: datetime, interval: str) -> dict[str, int]:
        return {}

