"""EmployeeRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import EmployeeNotFoundError
from models import Employee


class EmployeeRepository:
    """SQLite repository for Employee over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, employee: Employee) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO employees (first_name, last_name, email, phone, position, department_id, hire_date, salary, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (employee.first_name, employee.last_name, employee.email, employee.phone, employee.position, employee.department_id, employee.hire_date, employee.salary, employee.is_active),
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

    def list(self, first_name: Optional[Any] = None, last_name: Optional[Any] = None, email: Optional[Any] = None, position: Optional[Any] = None, department_id: Optional[Any] = None, hire_date: Optional[Any] = None, hire_date_end: Optional[Any] = None, salary: Optional[Any] = None, salary_end: Optional[Any] = None, is_active: Optional[Any] = None) -> List[Employee]:
        with self.db.connect() as conn:
            query = "SELECT * FROM employees WHERE 1=1"
            params: List[Any] = []
            if first_name is not None:
                query += ' AND first_name = ?'
                params.append(first_name)
            if last_name is not None:
                query += ' AND last_name = ?'
                params.append(last_name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if position is not None:
                query += ' AND position = ?'
                params.append(position)
            if department_id is not None:
                query += ' AND department_id = ?'
                params.append(department_id)
            if hire_date is not None:
                query += ' AND hire_date >= ?'
                params.append(hire_date)
            if hire_date_end is not None:
                query += ' AND hire_date <= ?'
                params.append(hire_date_end)
            if salary is not None:
                query += ' AND salary >= ?'
                params.append(salary)
            if salary_end is not None:
                query += ' AND salary <= ?'
                params.append(salary_end)
            if is_active is not None:
                query += ' AND is_active = ?'
                params.append(is_active)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['first_name', 'last_name', 'email', 'phone', 'position', 'department_id', 'hire_date', 'salary', 'is_active']
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
                raise EmployeeNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM employees WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_employees_by_department(self, department_id: int) -> list[Employee]:
        return self.list(
            department_id=department_id,
        )

    def get_employees_by_position(self, position: str) -> list[Employee]:
        return self.list(
            position=position,
        )

    def get_employees_by_salary_range(self, min_salary: float, max_salary: float) -> list[Employee]:
        return self.list(
            salary=min_salary,
            salary_end=max_salary,
        )

    def get_employees_with_active_status(self) -> list[Employee]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM employees WHERE is_active = ?', (True,)).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def get_department_head_count(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT d.name, COUNT(e.id) AS head_count FROM departments d LEFT JOIN employees e ON d.id = e.department_id AND e.is_active = 1 GROUP BY d.name').fetchall()
            return {row['name']: row['head_count'] for row in rows}

    def get_total_employees_by_department(self) -> dict[int, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT o.name AS k, SUM(e.salary) AS v FROM employees e JOIN departments o ON e.department_id = o.id GROUP BY o.name",
            ).fetchall()
            return {r["k"]: int(r["v"] or 0) for r in rows}

    def get_employees_with_hire_date_range(self, start_date: date, end_date: date) -> list[Employee]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM employees WHERE hire_date >= ? AND hire_date <= ?", ((start_date, end_date))
            ).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def search_employees_by_name(self, query: str) -> list[Employee]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM employees WHERE (first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR position LIKE ?)",
                ("%" + query + "%", "%" + query + "%", "%" + query + "%", "%" + query + "%", "%" + query + "%")
            ).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def get_employee_count_in_department(self, department_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(salary), 0) AS v FROM employees WHERE department_id = ?",
                (department_id,)
            ).fetchone()
            return int(row["v"])

    def get_employees_with_manager_info(self) -> list[Employee]:
        return []

