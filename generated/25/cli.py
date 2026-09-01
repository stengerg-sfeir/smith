import click
from database import Database
from employee_service import EmployeeService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('department-list')
def department_list():
    """department/list"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.list_department()

@cli.command('department-add')
@click.option('--name', required=True)
@click.option('--description')
def department_add(name, description):
    """department/add"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.add_department(name=name, description=description)

@cli.command('department-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
def department_update(id, name, description):
    """department/update"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.update_department(id=id, name=name, description=description)

@cli.command('department-delete')
@click.option('--id', type=int, required=True)
def department_delete(id):
    """department/delete"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.delete_department(id=id)


if __name__ == "__main__":
    cli()

