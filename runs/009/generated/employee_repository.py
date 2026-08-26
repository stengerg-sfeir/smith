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
                "INSERT INTO employees (name, email, age, salary) VALUES (?, ?, ?, ?)",
                (employee.name, employee.email, employee.age, employee.salary),
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

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, age: Optional[Any] = None, age_lte: Optional[Any] = None, salary: Optional[Any] = None, salary_lte: Optional[Any] = None) -> List[Employee]:
        with self.db.connect() as conn:
            query = "SELECT * FROM employees WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if age is not None:
                query += ' AND age >= ?'
                params.append(age)
            if age_lte is not None:
                query += ' AND age <= ?'
                params.append(age_lte)
            if salary is not None:
                query += ' AND salary >= ?'
                params.append(salary)
            if salary_lte is not None:
                query += ' AND salary <= ?'
                params.append(salary_lte)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Employee(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'age', 'salary']
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

    def get_employee_by_email(self, email: str) -> Optional[Employee]:
        return self.list(
            email=email,
        )

    def get_employees_by_age_range(self, min_age: int, max_age: int) -> list[Employee]:
        return self.list(
            age=min_age,
            age_lte=max_age,
        )

    def get_employees_with_salary_above(self, min_salary: float) -> list[Employee]:
        return self.list(
            salary=min_salary,
        )

    def count_employees_by_age_group(self) -> dict[str, int]:
        age_groups = {'under_18': 0, '18_25': 0, '26_35': 0, '36_50': 0, 'over_50': 0}
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("\n                SELECT \n                    CASE \n                        WHEN age < 18 THEN 'under_18'\n                        WHEN age BETWEEN 18 AND 25 THEN '18_25'\n                        WHEN age BETWEEN 26 AND 35 THEN '26_35'\n                        WHEN age BETWEEN 36 AND 50 THEN '36_50'\n                        ELSE 'over_50'\n                    END AS age_group\n                FROM employees\n            ")
            rows = cursor.fetchall()
            for row in rows:
                age_group = row[0]
                age_groups[age_group] += 1
        return age_groups

    def get_total_salary_spent(self) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(salary), 0) AS v FROM employees",
            ).fetchone()
            return float(row["v"])

    def get_average_salary(self) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(salary), 0) AS v FROM employees",
            ).fetchone()
            return float(row["v"])

    def get_employees_with_higher_salary_than_average(self) -> list[Employee]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT * FROM employees\n                WHERE salary > (\n                    SELECT AVG(salary) FROM employees\n                )\n            ')
            rows = cursor.fetchall()
            return [Employee(**dict(r)) for r in rows]

    def get_employees_with_valid_email_and_age_range(self, min_age: int, max_age: int) -> list[Employee]:
        return self.list(
            age=min_age,
            age_lte=max_age,
        )

    def get_employees_with_salary_in_range(self, min_salary: float, max_salary: float) -> list[Employee]:
        return self.list(
            salary=min_salary,
            salary_lte=max_salary,
        )

