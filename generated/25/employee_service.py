"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from database import Database
from department_repository import DepartmentRepository
from employee_repository import EmployeeRepository
from exceptions import (
    InvalidDepartmentIdError,
)
from models import Employee


class EmployeeService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.department_repo = DepartmentRepository(db)
        self.employee_repo = EmployeeRepository(db)

    def create_employee(self, first_name: str, last_name: str, email: str, department_id: int, hire_date: date) -> None:
        department = self.department_repo.get_by_id(department_id)
        if not department:
            raise InvalidDepartmentIdError(f'Department with id {department_id} not found')
        employee = Employee(first_name=first_name, last_name=last_name, email=email, department_id=department_id, hire_date=hire_date, is_active=True)
        self.employee_repo.create(employee)

    def get_employees_by_department(self, department_id: int, active_only: bool, min_hire_date: Optional[date]=None, max_hire_date: Optional[date]=None) -> List[Employee]:
        employees = self.employee_repo.list_employees_by_department(department_id=department_id, active_only=active_only, min_hire_date=min_hire_date, max_hire_date=max_hire_date)
        return employees

    def list_employees_with_department_names(self, department_id: int, page: int, page_size: int) -> List[Employee]:
        employees = self.employee_repo.list_employees_with_department_names(department_id=department_id, page=page, page_size=page_size)
        return employees

    def get_employee_count_by_department(self, department_id: int) -> int:
        return self.employee_repo.get_employee_count_by_department(department_id)

    def export_employees_to_csv(self, file_path: str, department_id: int, active_only: bool) -> None:
        rows = self.employee_repo.list(department_id=department_id, )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'first_name', 'last_name', 'email',
                'department_id', 'hire_date', 'is_active',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.first_name, row.last_name, row.email,
                    row.department_id, row.hire_date, row.is_active,
                ])

    def find_duplicate_employees_by_department(self, department_id: int) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.employee_repo.list(department_id=department_id):
            key = (row.first_name, row.last_name)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'first_name': key[0],
                    'last_name': key[1],
                    'count': len(group),
                })
        return results

    def get_employees_hired_in_period(self, start_date: date, end_date: date) -> List[Employee]:
        employees = self.employee_repo.get_employees_with_hire_date_range(start_date=start_date, end_date=end_date)
        return employees

