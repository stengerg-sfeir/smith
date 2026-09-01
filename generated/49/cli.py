import click
from database import Database
from employee_service import EmployeeService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('department-list')
@click.option('--name')
@click.option('--description')
@click.option('--manager-id')
def department_list(name, description, manager_id):
    """department/list"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.list_department(name=name, description=description, manager_id=manager_id)

@cli.command('employee-search')
@click.option('--term', required=True)
def employee_search(term):
    """employee/search"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.search_employee(term=term)


if __name__ == "__main__":
    cli()

