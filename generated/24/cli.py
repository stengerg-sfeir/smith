import click
from database import Database
from project_service import ProjectService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('project-list')
@click.option('--title')
@click.option('--description')
@click.option('--created-at')
@click.option('--created-at-end')
def project_list(title, description, created_at, created_at_end):
    """project/list"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_project(title=title, description=description, created_at=created_at, created_at_end=created_at_end)

@cli.command('project-add')
@click.option('--title', required=True)
@click.option('--description')
def project_add(title, description):
    """project/add"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.add_project(title=title, description=description)

@cli.command('project-delete')
@click.option('--id', type=int, required=True)
def project_delete(id):
    """project/delete"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.delete_project(id=id)

@cli.command('task-update')
@click.option('--id', type=int, required=True)
@click.option('--title')
@click.option('--description')
@click.option('--status')
@click.option('--priority', type=int)
@click.option('--project-id', type=int)
def task_update(id, title, description, status, priority, project_id):
    """task/update"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.update_task(id=id, title=title, description=description, status=status, priority=priority, project_id=project_id)


if __name__ == "__main__":
    cli()

