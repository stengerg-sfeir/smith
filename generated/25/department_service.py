"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from department_repository import DepartmentRepository
from employee_repository import EmployeeRepository
from models import Department


class EmployeeService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.department_repo = DepartmentRepository(db)
        self.employee_repo = EmployeeRepository(db)

    def create_department(self, name: str, description: Optional[str] = None) -> None:
        department = Department(name=name, description=description)
        return self.department_repo.create(department)

    def get_department_by_id(self, department_id: int) -> Optional[Department]:
        return self.department_repo.get_by_id(department_id)

    def list_departments_with_employee_count(self, active_only: bool, min_hire_date: Optional[date]=None, max_hire_date: Optional[date]=None) -> List[Dict[str, Any]]:
        """
            Lists departments with employee counts based on active status and hire date range.
            """
        departments = self.department_repo.list_departments_with_employee_count(active_only=active_only, min_hire_date=min_hire_date, max_hire_date=max_hire_date)
        result = []
        for dept in departments:
            result.append({'id': dept.id, 'name': dept.name, 'description': dept.description, 'employee_count': self.employee_repo.get_employee_count_by_department(dept.id)})
        return result

    def get_department_summary_by_name(self) -> Dict[str, Any]:
        """
            Returns a summary of departments by name, including employee counts.
            """
        summary = self.department_repo.get_department_summary_by_name()
        return summary

    def list_departments_with_active_employee_count(self, page: int, page_size: int) -> List[Department]:
        """
            Lists departments with active employee counts, paginated.
            """
        departments = self.department_repo.list_departments_with_active_employee_count(page=page, page_size=page_size)
        return departments

    def get_departments_with_hire_date_range(self, start_date: date, end_date: date) -> List[Department]:
        """
            Retrieves departments that have employees hired within the specified date range.
            """
        departments = self.department_repo.get_departments_with_hire_date_range(start_date=start_date, end_date=end_date)
        return departments

