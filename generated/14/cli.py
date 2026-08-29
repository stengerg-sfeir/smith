import click
from database import Database
from project_service import ProjectService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('project-create')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--status', required=True)
def project_create(name, description, status):
    """project/create"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.create_project(name=name, description=description, status=status)

@cli.command('project-update')
@click.option('--project-id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--status')
def project_update(project_id, name, description, status):
    """project/update"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.update_project(project_id=project_id, name=name, description=description, status=status)

@cli.command('project-list')
@click.option('--status')
@click.option('--query')
def project_list(status, query):
    """project/list"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_projects(status=status, query=query)

@cli.command('list-active')
def list_active():
    """project/list/active"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_active_projects()

@cli.command('project-delete')
@click.option('--project-id', type=int, required=True)
def project_delete(project_id):
    """project/delete"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.delete_project(project_id=project_id)

@cli.command('project-export')
@click.option('--file-path', required=True)
@click.option('--status-filter')
def project_export(file_path, status_filter):
    """project/export"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.export_projects_to_csv(file_path=file_path, status_filter=status_filter)

@cli.command('project-stats')
def project_stats():
    """project/stats"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_stats()


if __name__ == "__main__":
    cli()

