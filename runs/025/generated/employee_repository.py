"""EmployeeRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Employee


class EmployeeRepository:
    """SQLite repository for Employee over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, employee: Employee) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO employees (first_name, last_name, email, department_id, hire_date, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                (employee.first_name, employee.last_name, employee.email, employee.department_id, employee.hire_date, employee.is_active),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Employee]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM employees WHERE id = ?", (id,)
            ).fetchone()
            return Employee(**dict(row)) if row else None

    def get_all(self) -> List[Employee]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM employees ORDER BY id"
            ).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def list(self, department_id: Optional[Any] = None, hire_date: Optional[Any] = None, email: Optional[Any] = None, first_name: Optional[Any] = None, last_name: Optional[Any] = None, max_hire_date: Optional[Any] = None) -> List[Employee]:
        with self.db.connect() as conn:
            query = "SELECT * FROM employees WHERE 1=1"
            params: List[Any] = []
            if department_id is not None:
                query += ' AND department_id = ?'
                params.append(department_id)
            if hire_date is not None:
                query += ' AND hire_date >= ?'
                params.append(hire_date)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if first_name is not None:
                query += ' AND first_name = ?'
                params.append(first_name)
            if last_name is not None:
                query += ' AND last_name = ?'
                params.append(last_name)
            if max_hire_date is not None:
                query += ' AND hire_date <= ?'
                params.append(max_hire_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['first_name', 'last_name', 'email', 'department_id', 'hire_date', 'is_active']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE employees SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM employees WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def list_employees_by_department(self, department_id: int, active_only: bool, min_hire_date: date, max_hire_date: date) -> list[Employee]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM employees r JOIN departments o ON r.department_id = o.id WHERE o.name = ? AND r.hire_date >= ? AND r.hire_date <= ?",
                (department_id, min_hire_date, max_hire_date)
            ).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def get_employee_count_by_department(self, department_id: int) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) AS count FROM employees WHERE department_id = ?', (department_id,)).fetchone()
            return rows[0] if rows else 0

    def get_department_employee_summary(self) -> dict[str, any]:
        with self.db.connect() as conn:
            rows = conn.execute("\n                SELECT \n                    d.name AS department_name,\n                    COUNT(e.id) AS employee_count,\n                    AVG(strftime('%Y', e.hire_date)) AS avg_hire_year\n                FROM departments d\n                LEFT JOIN employees e ON d.id = e.department_id\n                GROUP BY d.name\n                ").fetchall()
            result = {}
            for row in rows:
                result[row[0]] = {'employee_count': row[1], 'avg_hire_year': row[2]}
            return result

    def list_employees_with_department_names(self, department_id: int, page: int, page_size: int) -> list[Employee]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM employees WHERE department_id = ? LIMIT ? OFFSET ?",
                (department_id, page_size, (page - 1) * page_size)
            ).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def get_employees_with_hire_date_range(self, start_date: date, end_date: date) -> list[Employee]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM employees WHERE hire_date >= ? AND hire_date <= ?", ((start_date, end_date))
            ).fetchall()
            return [Employee(**dict(r)) for r in rows]

