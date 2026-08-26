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
                "INSERT INTO projects (name, description, status, created_at, updated_at, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
                (project.name, project.description, project.status, project.created_at, project.updated_at, project.deleted_at),
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

    def list(self, name: Optional[Any] = None, status: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, description: Optional[Any] = None) -> List[Project]:
        with self.db.connect() as conn:
            query = "SELECT * FROM projects WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Project(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'status', 'created_at', 'updated_at', 'deleted_at']
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

    def get_project_by_name(self, name: str) -> Optional[Project]:
        return self.list(
            name=name,
        )

    def list_projects_by_status(self, status: str) -> list[Project]:
        return self.list(
            status=status,
        )

    def get_project_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM projects",
            ).fetchone()
            return int(row["n"])

    def list_active_projects(self) -> list[Project]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects WHERE status = ? AND deleted_at IS NULL', ('active',))
            rows = cursor.fetchall()
            return [Project(**dict(r)) for r in rows]

    def list_projects_with_pagination(self, page: int, page_size: int) -> list[Project]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * page_size
            cursor.execute('SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?', (page_size, offset))
            rows = cursor.fetchall()
            return [Project(**dict(r)) for r in rows]

    def get_project_stats(self) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("\n                SELECT \n                    COUNT(*) AS total_projects,\n                    COUNT(CASE WHEN status = 'active' THEN 1 END) AS active_projects,\n                    COUNT(CASE WHEN status = 'inactive' THEN 1 END) AS inactive_projects\n                FROM projects \n                WHERE deleted_at IS NULL\n            ")
            row = cursor.fetchone()
            return {'total_projects': row[0], 'active_projects': row[1], 'inactive_projects': row[2]}

    def search_projects(self, query: str, status_filter: Optional[str]=None) -> list[Project]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            query = f'%{query}%'
            conditions = ['description LIKE ?']
            params = [query]
            if status_filter:
                conditions.append('status = ?')
                params.append(status_filter)
            query_parts = ' AND '.join(conditions)
            cursor.execute(f'SELECT * FROM projects WHERE deleted_at IS NULL AND {query_parts}', params)
            rows = cursor.fetchall()
            return [Project(**dict(r)) for r in rows]

