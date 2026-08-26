import click
from database import Database
from employee_service import EmployeeService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('list-employees')
@click.option('--department-id', type=int, required=True)
@click.option('--active-only', is_flag=True, default=False)
@click.option('--min-hire-date')
@click.option('--max-hire-date')
def list_employees(department_id, active_only, min_hire_date, max_hire_date):
    """department/list/employees"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employees_by_department(department_id=department_id, active_only=active_only, min_hire_date=min_hire_date, max_hire_date=max_hire_date)

@cli.command('list-with_department_names')
@click.option('--department-id', type=int, required=True)
@click.option('--page', type=int)
@click.option('--page-size', type=int)
def list_with_department_names(department_id, page, page_size):
    """department/list/with_department_names"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.list_employees_with_department_names(department_id=department_id, page=page, page_size=page_size)

@cli.command('create-add')
@click.option('--first-name', required=True)
@click.option('--last-name', required=True)
@click.option('--email', required=True)
@click.option('--department-id', type=int, required=True)
@click.option('--hire-date')
def create_add(first_name, last_name, email, department_id, hire_date):
    """employee/create/add"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.create_employee(first_name=first_name, last_name=last_name, email=email, department_id=department_id, hire_date=hire_date)

@cli.command('employee-export')
@click.option('--file-path', required=True)
@click.option('--department-id', type=int, required=True)
@click.option('--active-only', is_flag=True, default=False)
def employee_export(file_path, department_id, active_only):
    """employee/export"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.export_employees_to_csv(file_path=file_path, department_id=department_id, active_only=active_only)

@cli.command('find-duplicates')
@click.option('--department-id', type=int, required=True)
def find_duplicates(department_id):
    """employee/find/duplicates"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.find_duplicate_employees_by_department(department_id=department_id)

@cli.command('employee-count')
@click.option('--department-id', type=int, required=True)
def employee_count(department_id):
    """employee/count"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employee_count_by_department(department_id=department_id)

@cli.command('employee-hired_in_period')
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def employee_hired_in_period(start_date, end_date):
    """employee/hired_in_period"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employees_hired_in_period(start_date=start_date, end_date=end_date)


if __name__ == "__main__":
    cli()

