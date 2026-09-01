import click
from database import Database
from task_service import TaskService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('project-add')
@click.option('--name', required=True)
@click.option('--description')
def project_add(name, description):
    """project/add"""
    svc = TaskService(Database(DB_PATH))
    result = svc.add_project(name=name, description=description)

@cli.command('person-assign')
@click.option('--id', type=int, required=True)
def person_assign(id):
    """person/assign"""
    svc = TaskService(Database(DB_PATH))
    result = svc.assign_person(id=id)

@cli.command('project-list')
def project_list():
    """project/list"""
    svc = TaskService(Database(DB_PATH))
    result = svc.list_project()

@cli.command('task-list')
@click.option('--project-id')
@click.option('--status')
def task_list(project_id, status):
    """task/list"""
    svc = TaskService(Database(DB_PATH))
    result = svc.list_task(project_id=project_id, status=status)


if __name__ == "__main__":
    cli()

