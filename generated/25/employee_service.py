"""Service layer."""
from __future__ import annotations

from typing import Optional

from database import Database
from department_repository import DepartmentRepository
from employee_repository import EmployeeRepository
from models import Department


class EmployeeService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.department_repo = DepartmentRepository(db)
        self.employee_repo = EmployeeRepository(db)

    def list_department(self) -> list[Department]:
        return self.department_repo.list()

    def add_department(self, name: str, description: Optional[str] = None) -> None:
        department = Department(name=name, description=description)
        return self.department_repo.create(department)

    def update_department(self, id: int, name: str, description: Optional[str] = None) -> None:
        data = {k: v for k, v in {'name': name, 'description': description}.items() if v is not None}
        return self.department_repo.update(id, data)

    def delete_department(self, id: int) -> None:
        return self.department_repo.delete(id)

