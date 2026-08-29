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

    def list(self, description: Optional[Any] = None, name: Optional[Any] = None, max_hire_date: Optional[Any] = None, min_hire_date: Optional[Any] = None) -> List[Department]:
        with self.db.connect() as conn:
            query = "SELECT * FROM departments WHERE 1=1"
            params: List[Any] = []
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if max_hire_date is not None:
                query += ' AND id <= ?'
                params.append(max_hire_date)
            if min_hire_date is not None:
                query += ' AND id >= ?'
                params.append(min_hire_date)
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
            row = conn.execute('SELECT * FROM departments WHERE id = ?', (department_id,)).fetchone()
            return Department(**row) if row else None

    def list_departments_with_employee_count(self, active_only: bool, min_hire_date: str, max_hire_date: str) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            query = '\n                SELECT d.id, d.name, d.description, COUNT(e.id) AS employee_count\n                FROM departments d\n                LEFT JOIN employees e ON e.department_id = d.id\n                WHERE 1=1\n            '
            params = []
            if active_only:
                query += ' AND e.is_active = 1'
                params.append(1)
            if min_hire_date:
                query += ' AND e.hire_date >= ?'
                params.append(min_hire_date)
            if max_hire_date:
                query += ' AND e.hire_date <= ?'
                params.append(max_hire_date)
            query += ' GROUP BY d.id, d.name, d.description'
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_total_employees_in_department(self, department_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) AS count FROM employees WHERE department_id = ?', (department_id,)).fetchone()
            return row[0] if row else 0

    def get_department_summary_by_name(self) -> dict[str, any]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT name, COUNT(*) AS employee_count, AVG(STRLEN(first_name)) AS avg_first_name_length FROM departments d LEFT JOIN employees e ON e.department_id = d.id GROUP BY d.name').fetchall()
            result = {}
            for row in rows:
                result[row['name']] = {'employee_count': row['employee_count'], 'avg_first_name_length': row['avg_first_name_length']}
            return result

    def list_departments_with_active_employee_count(self, page: int, page_size: int) -> list[Department]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM departments LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size)
            ).fetchall()
            return [Department(**dict(r)) for r in rows]

    def get_departments_with_hire_date_range(self, start_date: date, end_date: date) -> list[Department]:
        return []

