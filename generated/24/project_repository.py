"""ProjectRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import ProjectNotFoundError
from models import Project


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
            query = '\n                SELECT \n                    COUNT(*) AS total_tasks,\n                    COUNT(CASE WHEN status = ? THEN 1 END) AS completed_tasks,\n                    COUNT(CASE WHEN status = ? THEN 1 END) AS in_progress_tasks,\n                    COUNT(CASE WHEN status = ? THEN 1 END) AS pending_tasks\n                FROM tasks \n                WHERE project_id = ? \n                  AND status = ? \n                  AND priority = ?\n            '
            rows = conn.execute(query, (status_filter, status_filter, status_filter, project_id, status_filter, priority_filter)).fetchone()
            if rows is None:
                return {}
            return {'total_tasks': rows[0], 'completed_tasks': rows[1], 'in_progress_tasks': rows[2], 'pending_tasks': rows[3]}

    def list_projects_with_task_count(self) -> list[dict]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    p.id,\n                    p.title,\n                    p.description,\n                    COUNT(t.id) AS task_count\n                FROM projects p\n                LEFT JOIN tasks t ON p.id = t.project_id\n                GROUP BY p.id\n            '
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def get_project_with_tasks(self, project_id: int) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    p.id,\n                    p.title,\n                    p.description,\n                    p.created_at,\n                    p.updated_at,\n                    t.id AS task_id,\n                    t.title AS task_title,\n                    t.description AS task_description,\n                    t.status,\n                    t.priority,\n                    t.created_at AS task_created_at,\n                    t.updated_at AS task_updated_at\n                FROM projects p\n                LEFT JOIN tasks t ON p.id = t.project_id\n                WHERE p.id = ?\n            '
            rows = conn.execute(query, (project_id,)).fetchall()
            project_data = next((row for row in rows if row['id'] == project_id), None)
            if not project_data:
                raise ProjectNotFoundError(f'Project with id {project_id} not found')
            project_dict = {'id': project_data['id'], 'title': project_data['title'], 'description': project_data['description'], 'created_at': project_data['created_at'], 'updated_at': project_data['updated_at'], 'tasks': []}
            for row in rows:
                if row['id'] == project_id:
                    project_dict['tasks'].append({'id': row['task_id'], 'title': row['task_title'], 'description': row['task_description'], 'status': row['status'], 'priority': row['priority'], 'created_at': row['task_created_at'], 'updated_at': row['task_updated_at']})
            return project_dict

    def get_task_stats_by_project(self) -> dict:
        with self.db.connect() as conn:
            query = "\n                SELECT \n                    p.id,\n                    p.title,\n                    COUNT(t.id) AS total_tasks,\n                    SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,\n                    SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_tasks,\n                    SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks\n                FROM projects p\n                LEFT JOIN tasks t ON p.id = t.project_id\n                GROUP BY p.id\n            "
            rows = conn.execute(query).fetchall()
            result = {}
            for row in rows:
                result[row['id']] = {'title': row['title'], 'total_tasks': row['total_tasks'], 'completed_tasks': row['completed_tasks'], 'in_progress_tasks': row['in_progress_tasks'], 'pending_tasks': row['pending_tasks']}
            return result

    def search_tasks_by_title(self, query: str, project_id: int) -> list[dict]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    t.id,\n                    t.title,\n                    t.description,\n                    t.status,\n                    t.priority,\n                    t.created_at,\n                    t.updated_at\n                FROM tasks t\n                WHERE t.project_id = ? \n                  AND t.title LIKE ?\n            '
            rows = conn.execute(query, (project_id, f'%{query}%')).fetchall()
            return [dict(row) for row in rows]

    def get_project_completion_rate(self, project_id: int) -> float:
        with self.db.connect() as conn:
            query = "\n                SELECT \n                    COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed,\n                    COUNT(*) AS total\n                FROM tasks \n                WHERE project_id = ?\n            "
            row = conn.execute(query, (project_id,)).fetchone()
            if row is None or row[1] == 0:
                return 0.0
            return round(row[0] / row[1], 2)

    def list_tasks_by_status_and_priority(self, status: str, priority: int) -> list[dict]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    t.id,\n                    t.title,\n                    t.description,\n                    t.status,\n                    t.priority,\n                    t.created_at,\n                    t.updated_at\n                FROM tasks t\n                WHERE t.status = ? \n                  AND t.priority = ?\n            '
            rows = conn.execute(query, (status, priority)).fetchall()
            return [dict(row) for row in rows]

    def get_total_tasks_by_status(self) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    status,\n                    COUNT(*) AS task_count\n                FROM tasks\n                GROUP BY status\n            '
            rows = conn.execute(query).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_project_task_distribution(self) -> dict:
        with self.db.connect() as conn:
            query = "\n                SELECT \n                    p.id,\n                    p.title,\n                    COUNT(t.id) AS task_count,\n                    SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,\n                    SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,\n                    SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS pending\n                FROM projects p\n                LEFT JOIN tasks t ON p.id = t.project_id\n                GROUP BY p.id\n            "
            rows = conn.execute(query).fetchall()
            return {row['id']: {'title': row['title'], 'task_count': row['task_count'], 'completed': row['completed'], 'in_progress': row['in_progress'], 'pending': row['pending']} for row in rows}

