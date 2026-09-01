"""ProjectRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Person, Project, Task


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

    def get_project_by_name(self, name: str) -> Optional[Project]:
        return self.list(
            name=name,
        )

    def get_tasks_by_project_id(self, project_id: int, status: Optional[str]=None, due_date_after: Optional[str]=None, due_date_before: Optional[str]=None) -> list[Task]:
        query = 'SELECT * FROM tasks WHERE project_id = ?'
        params = [project_id]
        if status is not None:
            query += ' AND status = ?'
            params.append(status)
        if due_date_after is not None:
            query += ' AND due_date > ?'
            params.append(due_date_after)
        if due_date_before is not None:
            query += ' AND due_date < ?'
            params.append(due_date_before)
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_people_assigned_to_project(self, project_id: int) -> list[Person]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT DISTINCT p.* FROM people p JOIN tasks t ON p.id = t.assigned_to WHERE t.project_id = ?', [project_id]).fetchall()
            return [Person(**dict(r)) for r in rows]

    def get_project_with_task_summary(self, project_id: int) -> dict[str, any]:
        with self.db.connect() as conn:
            row = conn.execute("\n                SELECT \n                    p.id, p.name, p.description, \n                    COUNT(t.id) as total_tasks, \n                    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) as completed_tasks, \n                    COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) as in_progress_tasks, \n                    COUNT(CASE WHEN t.status = 'pending' THEN 1 END) as pending_tasks\n                FROM projects p\n                LEFT JOIN tasks t ON p.id = t.project_id\n                WHERE p.id = ?\n                GROUP BY p.id, p.name, p.description\n                ", [project_id]).fetchone()
            if row is None:
                return {}
            return {'id': row[0], 'name': row[1], 'description': row[2], 'total_tasks': row[3], 'completed_tasks': row[4], 'in_progress_tasks': row[5], 'pending_tasks': row[6]}

    def get_overdue_tasks_count(self, project_id: Optional[int]=None) -> int:
        query = 'SELECT COUNT(*) FROM tasks WHERE due_date < CURRENT_DATE'
        params = []
        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        with self.db.connect() as conn:
            row = conn.execute(query, params).fetchone()
            return row[0] if row else 0

    def get_project_completion_rate(self, project_id: Optional[int]=None) -> float:
        query = "\n        SELECT \n            COUNT(CASE WHEN t.status = 'completed' THEN 1 END) * 100.0 / \n            NULLIF(COUNT(t.id), 0) as completion_rate\n        FROM tasks t\n        WHERE 1=1\n        "
        params = []
        if project_id is not None:
            query += ' AND t.project_id = ?'
            params.append(project_id)
        with self.db.connect() as conn:
            row = conn.execute(query, params).fetchone()
            rate = row[0] if row else 0.0
            return float(rate)

    def get_tasks_by_status_and_due_date_range(self, status: str, due_date_from: Optional[str]=None, due_date_to: Optional[str]=None) -> list[Task]:
        query = 'SELECT * FROM tasks WHERE status = ?'
        params = [status]
        if due_date_from is not None:
            query += ' AND due_date >= ?'
            params.append(due_date_from)
        if due_date_to is not None:
            query += ' AND due_date <= ?'
            params.append(due_date_to)
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_project_team_size(self, project_id: int) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT DISTINCT p.id FROM people p JOIN tasks t ON p.id = t.assigned_to WHERE t.project_id = ?', [project_id]).fetchall()
            return len(rows)

