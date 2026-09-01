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
def project_add(name, description):
    """project/add"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.add_project(name=name, description=description)

@cli.command('priority-set')
@click.option('--id', type=int, required=True)
def priority_set(id):
    """priority/set"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.set_priority(id=id)

@cli.command('status-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
def status_update(id, name):
    """status/update"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.update_status(id=id, name=name)

@cli.command('project-list')
@click.option('--name')
@click.option('--description')
@click.option('--created-at')
@click.option('--created-at-end')
@click.option('--updated-at')
@click.option('--updated-at-end')
def project_list(name, description, created_at, created_at_end, updated_at, updated_at_end):
    """project/list"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_project(name=name, description=description, created_at=created_at, created_at_end=created_at_end, updated_at=updated_at, updated_at_end=updated_at_end)


if __name__ == "__main__":
    cli()

