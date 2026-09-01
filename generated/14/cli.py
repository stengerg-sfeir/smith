import click
from database import Database
from project_service import ProjectService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('project-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--status', required=True)
def project_add(name, description, status):
    """project/add"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.add_project(name=name, description=description, status=status)

@cli.command('project-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--status')
def project_update(id, name, description, status):
    """project/update"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.update_project(id=id, name=name, description=description, status=status)

@cli.command('project-list')
@click.option('--name')
@click.option('--status')
@click.option('--created-at')
@click.option('--created-at-end')
def project_list(name, status, created_at, created_at_end):
    """project/list"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_project(name=name, status=status, created_at=created_at, created_at_end=created_at_end)

@cli.command('project-delete')
@click.option('--id', type=int, required=True)
def project_delete(id):
    """project/delete"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.delete_project(id=id)


if __name__ == "__main__":
    cli()

