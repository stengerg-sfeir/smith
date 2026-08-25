"""Service layer."""
from __future__ import annotations

import csv
from typing import Dict, List, Optional

from database import Database
from employee_repository import EmployeeRepository
from models import Employee


class EmployeeService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.employee_repo = EmployeeRepository(db)

    def create_employee(self, name: str, email: str, age: int, salary: float) -> bool:
        employee = Employee(name=name, email=email, age=age, salary=salary)
        return self.employee_repo.create(employee)

    def get_employee_by_email(self, email: str) -> Optional[Employee]:
        return self.employee_repo.get_employee_by_email(email)

    def get_employees_by_age_range(self, min_age: int, max_age: int) -> List[Employee]:
        return self.employee_repo.get_employees_by_age_range(min_age, max_age)

    def get_employees_with_salary_above(self, min_salary: float) -> List[Employee]:
        return self.employee_repo.get_employees_with_salary_above(min_salary)

    def count_employees_by_age_group(self) -> Dict[str, int]:
        results = {}
        for row in self.employee_repo.list():
            key = row.age
            results[key] = results.get(key, 0) + row.age
        return results

    def get_total_salary_spent(self) -> float:
        return self.employee_repo.get_total_salary_spent()

    def get_average_salary(self) -> float:
        return self.employee_repo.get_average_salary()

    def get_employees_with_higher_salary_than_average(self) -> List[Employee]:
        return self.employee_repo.get_employees_with_higher_salary_than_average()

    def get_employees_with_valid_email_and_age_range(self, min_age: int, max_age: int) -> List[Employee]:
        return self.employee_repo.get_employees_with_valid_email_and_age_range(min_age, max_age)

    def get_employees_with_salary_in_range(self, min_salary: float, max_salary: float) -> List[Employee]:
        return self.employee_repo.get_employees_with_salary_in_range(min_salary, max_salary)

    def export_employees_to_csv(self, file_path: str) -> None:
        rows = self.employee_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'email', 'age',
                'salary',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.name, row.email, row.age,
                    row.salary,
                ])

