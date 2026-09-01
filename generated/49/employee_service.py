"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from database import Database
from department_repository import DepartmentRepository
from employee_repository import EmployeeRepository
from models import Department, Employee


class EmployeeService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.department_repo = DepartmentRepository(db)
        self.employee_repo = EmployeeRepository(db)

    def list_department(self, name: Optional[str] = None, description: Optional[str] = None, manager_id: Optional[int] = None) -> List[Department]:
        return self.department_repo.list(name=name, description=description, manager_id=manager_id)

    def search_employee(self, term: str) -> List[Employee]:
        """
            Search for employees by name using a query term.
            The search is case-insensitive and matches first or last name.
            """
        if not term or not term.strip():
            return []
        query = term.strip().lower()
        matching_employees = self.employee_repo.search_employees_by_name(query)
        return matching_employees

