"""DepartmentRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import DepartmentNotFoundError
from models import Department


class DepartmentRepository:
    """SQLite repository for Department over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, department: Department) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO departments (name, description, manager_id) VALUES (?, ?, ?)",
                (department.name, department.description, department.manager_id),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Department]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM departments WHERE id = ?", (id,)
            ).fetchone()
            return Department(**dict(row)) if row else None

    def get_all(self) -> List[Department]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM departments ORDER BY id"
            ).fetchall()
            return [Department(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, description: Optional[Any] = None, manager_id: Optional[Any] = None) -> List[Department]:
        with self.db.connect() as conn:
            query = "SELECT * FROM departments WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if manager_id is not None:
                query += ' AND manager_id = ?'
                params.append(manager_id)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Department(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'manager_id']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE departments SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise DepartmentNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM departments WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_department_by_id(self, department_id: int) -> Optional[Department]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM departments WHERE id = ?', (department_id,)).fetchall()
            return [Department(**dict(r)) for r in rows] if rows else None

    def get_departments_by_name_prefix(self, prefix: str) -> list[Department]:
        return []

    def get_department_head_count(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT department_id AS k, COUNT(*) AS n FROM employees GROUP BY department_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_departments_with_employee_count(self) -> list[Department]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT d.id, d.name, d.description, d.manager_id \n                FROM departments d\n                LEFT JOIN employees e ON d.id = e.department_id\n                GROUP BY d.id, d.name, d.description, d.manager_id\n            ').fetchall()
            return [Department(**dict(r)) for r in rows]

    def get_departments_with_manager_info(self) -> list[Department]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT d.id, d.name, d.description, d.manager_id \n                FROM departments d\n            ').fetchall()
            return [Department(**dict(r)) for r in rows]

    def get_departments_with_active_employees(self) -> list[Department]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT d.id, d.name, d.description, d.manager_id \n                FROM departments d\n                LEFT JOIN employees e ON d.id = e.department_id AND e.is_active = 1\n                GROUP BY d.id, d.name, d.description, d.manager_id\n            ').fetchall()
            return [Department(**dict(r)) for r in rows]

    def get_department_summary_stats(self) -> dict[str, any]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT \n                    COUNT(*) AS total_departments,\n                    COUNT(CASE WHEN manager_id IS NOT NULL THEN 1 END) AS departments_with_manager,\n                    COUNT(CASE WHEN manager_id IS NULL THEN 1 END) AS departments_without_manager\n                FROM departments\n            ').fetchone()
            return {'total_departments': rows[0] if rows else 0, 'departments_with_manager': rows[1] if rows else 0, 'departments_without_manager': rows[2] if rows else 0}

