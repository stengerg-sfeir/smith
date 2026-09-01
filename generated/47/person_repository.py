"""PersonRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Person


class PersonRepository:
    """SQLite repository for Person over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, person: Person) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO people (name, email, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (person.name, person.email, person.role, person.created_at, person.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Person]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM people WHERE id = ?", (id,)
            ).fetchone()
            return Person(**dict(row)) if row else None

    def get_all(self) -> List[Person]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM people ORDER BY id"
            ).fetchall()
            return [Person(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, role: Optional[Any] = None) -> List[Person]:
        with self.db.connect() as conn:
            query = "SELECT * FROM people WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if role is not None:
                query += ' AND role = ?'
                params.append(role)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Person(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'role', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE people SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM people WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_people_by_role(self, role: Optional[str] = None) -> list[Person]:
        return self.list(
            role=role,
        )

    def get_people_assigned_to_tasks(self, project_id: Optional[int]=None) -> list[Person]:
        query = 'SELECT DISTINCT p.id, p.name, p.email, p.role, p.created_at, p.updated_at FROM people p JOIN tasks t ON p.id = t.assigned_to'
        if project_id is not None:
            query += ' WHERE t.project_id = ?'
        query += ' ORDER BY p.name'
        with self.db.connect() as conn:
            rows = conn.execute(query, (project_id,) if project_id is not None else ()).fetchall()
        return [Person(**dict(r)) for r in rows]

    def get_people_with_task_count(self) -> list[dict[str, any]]:
        query = 'SELECT p.id, p.name, p.email, p.role, COUNT(t.id) as task_count FROM people p LEFT JOIN tasks t ON p.id = t.assigned_to GROUP BY p.id, p.name, p.email, p.role ORDER BY task_count DESC'
        with self.db.connect() as conn:
            rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]

    def get_people_with_project_assignments(self, project_id: Optional[int]=None) -> list[dict[str, any]]:
        query = 'SELECT DISTINCT p.id, p.name, p.email, p.role FROM people p JOIN tasks t ON p.id = t.assigned_to'
        if project_id is not None:
            query += ' WHERE t.project_id = ?'
        query += ' ORDER BY p.name'
        with self.db.connect() as conn:
            rows = conn.execute(query, (project_id,) if project_id is not None else ()).fetchall()
        return [dict(r) for r in rows]

    def get_person_with_project_and_task_summary(self, person_id: int) -> dict[str, any]:
        query = "\n        SELECT \n            p.id, \n            p.name, \n            p.email, \n            p.role,\n            COUNT(t.id) as task_count,\n            COUNT(CASE WHEN t.status = 'completed' THEN 1 END) as completed_tasks,\n            COUNT(CASE WHEN t.status = 'pending' THEN 1 END) as pending_tasks,\n            COUNT(CASE WHEN t.status = 'overdue' THEN 1 END) as overdue_tasks,\n            GROUP_CONCAT(DISTINCT pr.name) as project_names\n        FROM people p\n        LEFT JOIN tasks t ON p.id = t.assigned_to\n        LEFT JOIN projects pr ON t.project_id = pr.id\n        WHERE p.id = ?\n        GROUP BY p.id, p.name, p.email, p.role\n        "
        with self.db.connect() as conn:
            row = conn.execute(query, (person_id,)).fetchone()
        return dict(row) if row else {}

    def get_total_people_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM people",
            ).fetchone()
            return int(row["n"])

    def get_people_by_email_domain(self, domain: str) -> list[Person]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM people WHERE (name LIKE ? OR email LIKE ? OR role LIKE ?)",
                ("%" + domain + "%", "%" + domain + "%", "%" + domain + "%")
            ).fetchall()
            return [Person(**dict(r)) for r in rows]

