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
                "INSERT INTO tasks (title, description, project_id, assigned_to, status, due_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task.title, task.description, task.project_id, task.assigned_to, task.status, task.due_date, task.created_at, task.updated_at),
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

    def list(self, description: Optional[Any] = None, project_id: Optional[Any] = None, status: Optional[Any] = None) -> List[Task]:
        with self.db.connect() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params: List[Any] = []
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if project_id is not None:
                query += ' AND project_id = ?'
                params.append(project_id)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'description', 'project_id', 'assigned_to', 'status', 'due_date', 'created_at', 'updated_at']
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

    def get_tasks_by_status_and_assignee(self, status: str, assignee_id: Optional[int] = None) -> list[Task]:
        return []

    def get_tasks_by_project_and_status(self, project_id: int, status: str) -> list[Task]:
        return self.list(
            project_id=project_id,
            status=status,
        )

    def get_tasks_with_person_details(self) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    t.id, \n                    t.title, \n                    t.description, \n                    t.due_date, \n                    t.status, \n                    t.project_id, \n                    p.id as person_id, \n                    p.name as person_name, \n                    p.email, \n                    p.role\n                FROM tasks t\n                LEFT JOIN people p ON t.assigned_to = p.id\n            '
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def get_tasks_due_within_next_7_days(self) -> list[Task]:
        return []

    def get_tasks_by_status_and_due_date_range(self, status: str, due_date_from: Optional[date] = None, due_date_to: Optional[date] = None) -> list[Task]:
        return []

    def get_tasks_with_project_and_assignee_summary(self) -> dict[str, any]:
        with self.db.connect() as conn:
            query = "\n                SELECT \n                    p.name as project_name,\n                    p.id as project_id,\n                    COUNT(t.id) as task_count,\n                    GROUP_CONCAT(DISTINCT p.name || ' -> ' || CASE \n                        WHEN a.name IS NULL THEN 'Unassigned' \n                        ELSE a.name \n                    END) as assignee_summary\n                FROM projects p\n                LEFT JOIN tasks t ON p.id = t.project_id\n                LEFT JOIN people a ON t.assigned_to = a.id\n                GROUP BY p.id, p.name\n            "
            rows = conn.execute(query).fetchall()
            result = {}
            for row in rows:
                project_name = row['project_name']
                task_count = row['task_count']
                assignee_summary = row['assignee_summary'] or 'No assignees'
                result[project_name] = {'task_count': task_count, 'assignee_summary': assignee_summary}
            return result

    def get_tasks_with_overdue_status(self) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE due_date IS NOT NULL AND due_date < date('now')"
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_tasks_by_person(self, person_id: Optional[int]=None) -> list[Task]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    t.id, \n                    t.title, \n                    t.description, \n                    t.due_date, \n                    t.status, \n                    t.project_id, \n                    t.assigned_to\n                FROM tasks t\n                WHERE t.assigned_to = ?\n            '
            rows = conn.execute(query, (person_id,)).fetchall()
            return [Task(**dict(row)) for row in rows]


    def get_tasks_by_project_id(self, project_id: int) -> List[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ?", (project_id,)
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

