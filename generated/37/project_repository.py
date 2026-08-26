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

    def get_project_with_tasks(self, project_id: int) -> Project:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchall()
            if not rows:
                raise ProjectNotFoundError(f'Project with id {project_id} not found')
            project_data = rows[0]
            project = Project(id=project_data['id'], name=project_data['name'], description=project_data['description'], created_at=project_data['created_at'], updated_at=project_data['updated_at'])
            return project

    def list_projects_with_task_count(self, status_filter: str, priority_filter: int, due_date_range: tuple[str, str]) -> list[Project]:
        with self.db.connect() as conn:
            query = '\n                SELECT p.id, p.name, p.description, p.created_at, p.updated_at\n                FROM projects p\n                LEFT JOIN tasks t ON p.id = t.project_id\n                WHERE 1=1\n            '
            params = []
            if status_filter:
                query += ' AND t.status = ?'
                params.append(status_filter)
            if priority_filter:
                query += ' AND t.priority = ?'
                params.append(priority_filter)
            if due_date_range:
                query += ' AND t.due_date BETWEEN ? AND ?'
                params.extend(due_date_range)
            query += ' GROUP BY p.id, p.name, p.description, p.created_at, p.updated_at'
            rows = conn.execute(query, params).fetchall()
            return [Project(id=row['id'], name=row['name'], description=row['description'], created_at=row['created_at'], updated_at=row['updated_at']) for row in rows]

    def get_project_tasks_summary(self, project_id: int) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, COUNT(*) as count FROM tasks WHERE project_id = ? GROUP BY status', (project_id,)).fetchall()
            summary = {}
            for row in rows:
                summary[row['status']] = row['count']
            return summary

    def get_overdue_tasks_count_by_project(self) -> dict[int, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT project_id AS k, COUNT(*) AS n FROM tasks GROUP BY project_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_project_completion_rate(self, project_id: int) -> float:
        with self.db.connect() as conn:
            total_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE project_id = ?', (project_id,)).fetchone()[0]
            if total_tasks == 0:
                return 0.0
            completed_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status = ?', (project_id, 'completed')).fetchone()[0]
            return completed_tasks / total_tasks

    def search_projects_by_name(self, query: str, limit: int) -> list[Project]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM projects WHERE name LIKE ? LIMIT ?', (f'%{query}%', limit)).fetchall()
            return [Project(id=row['id'], name=row['name'], description=row['description'], created_at=row['created_at'], updated_at=row['updated_at']) for row in rows]

    def get_tasks_by_status_and_priority(self, status: str, priority: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM tasks WHERE status = ? AND priority = ?', (status, priority)).fetchall()
            return [Task(id=row['id'], title=row['title'], description=row['description'], status=row['status'], priority=row['priority'], due_date=row['due_date'], created_at=row['created_at'], updated_at=row['updated_at']) for row in rows]

    def get_project_creation_trend(self, start_date: str, end_date: str, interval: str) -> dict[str, int]:
        with self.db.connect() as conn:
            query = 'SELECT substr(created_at, 1, 7) as month, COUNT(*) as count FROM projects WHERE created_at BETWEEN ? AND ? GROUP BY substr(created_at, 1, 7)'
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            trend = {}
            for row in rows:
                trend[row['month']] = row['count']
            return trend

