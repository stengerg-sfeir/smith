import click
from database import Database
from project_service import ProjectService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('project-delete')
@click.option('--id', type=int, required=True)
def project_delete(id):
    """project/delete"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.delete_project(id=id)


if __name__ == "__main__":
    cli()

