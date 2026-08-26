"""DepartmentRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Department


class DepartmentRepository:
    """SQLite repository for Department over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, department: Department) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO departments (name, description) VALUES (?, ?)",
                (department.name, department.description),
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

    def list(self, description: Optional[Any] = None, name: Optional[Any] = None) -> List[Department]:
        with self.db.connect() as conn:
            query = "SELECT * FROM departments WHERE 1=1"
            params: List[Any] = []
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Department(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description']
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
                return False
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
            return Department(**dict(rows[0])) if rows else None

    def list_departments_with_employee_count(self, active_only: bool, min_hire_date: date, max_hire_date: date) -> list[dict[str, any]]:
        raise NotImplementedError()

    def get_total_employees_in_department(self, department_id: int) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM employees WHERE department_id = ?', (department_id,)).fetchone()
            return rows[0] if rows else 0

    def get_department_summary_by_name(self) -> dict[str, any]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT name, COUNT(*) as employee_count FROM departments d LEFT JOIN employees e ON d.id = e.department_id GROUP BY d.name').fetchall()
            result = {}
            for row in rows:
                result[row['name']] = row['employee_count']
            return result

    def list_departments_with_active_employee_count(self, page: int, page_size: int) -> list[Department]:
        with self.db.connect() as conn:
            offset = page * page_size
            rows = conn.execute('SELECT d.* FROM departments d LEFT JOIN employees e ON d.id = e.department_id WHERE e.is_active = 1 GROUP BY d.id ORDER BY d.name LIMIT ? OFFSET ?', (page_size, offset)).fetchall()
            return [Department(**dict(r)) for r in rows]

    def get_departments_with_hire_date_range(self, start_date: date, end_date: date) -> list[Department]:
        raise NotImplementedError()

