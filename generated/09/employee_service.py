"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from database import Database
from employee_repository import EmployeeRepository
from models import Employee


class EmployeeService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.employee_repo = EmployeeRepository(db)

    def add_employee(self, name: str, email: str, age: int, salary: str) -> bool:
        employee = Employee(name=name, email=email, age=age, salary=salary)
        return self.employee_repo.create(employee)

    def list_employee(self, name: Optional[str] = None, email: Optional[str] = None, age: Optional[str] = None, age_lte: Optional[str] = None, salary: Optional[str] = None, salary_lte: Optional[str] = None) -> List[Employee]:
        return self.employee_repo.list(name=name, email=email, age=age, age_lte=age_lte, salary=salary, salary_lte=salary_lte)

    def update_employee(self, id: int, name: Optional[str] = None, email: Optional[str] = None, age: Optional[int] = None, salary: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'name': name, 'email': email, 'age': age, 'salary': salary}.items() if v is not None}
        return self.employee_repo.update(id, data)

    def delete_employee(self, id: int) -> bool:
        return self.employee_repo.delete(id)

