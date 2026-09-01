import click
from database import Database
from employee_service import EmployeeService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('employee-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--age', type=int, required=True)
@click.option('--salary', required=True)
def employee_add(name, email, age, salary):
    """employee/add"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.add_employee(name=name, email=email, age=age, salary=salary)

@cli.command('employee-list')
@click.option('--name')
@click.option('--email')
@click.option('--age')
@click.option('--age-lte')
@click.option('--salary')
@click.option('--salary-lte')
def employee_list(name, email, age, age_lte, salary, salary_lte):
    """employee/list"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.list_employee(name=name, email=email, age=age, age_lte=age_lte, salary=salary, salary_lte=salary_lte)

@cli.command('employee-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--email')
@click.option('--age', type=int)
@click.option('--salary')
def employee_update(id, name, email, age, salary):
    """employee/update"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.update_employee(id=id, name=name, email=email, age=age, salary=salary)

@cli.command('employee-delete')
@click.option('--id', type=int, required=True)
def employee_delete(id):
    """employee/delete"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.delete_employee(id=id)


if __name__ == "__main__":
    cli()

