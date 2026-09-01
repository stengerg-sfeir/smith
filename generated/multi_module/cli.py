import click
from database import Database
from task_service import TaskService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('task-list')
@click.option('--status')
@click.option('--limit', type=int)
@click.option('--offset', type=int)
def task_list(status, limit, offset):
    """task/list"""
    svc = TaskService(Database(DB_PATH))
    result = svc.list(status=status, limit=limit, offset=offset)

@cli.command('task-update')
@click.option('--task-id', type=int, required=True)
@click.option('--title')
@click.option('--description')
@click.option('--status')
def task_update(task_id, title, description, status):
    """task/update"""
    svc = TaskService(Database(DB_PATH))
    result = svc.update(task_id=task_id, title=title, description=description, status=status)

@cli.command('task-delete')
@click.option('--task-id', type=int, required=True)
def task_delete(task_id):
    """task/delete"""
    svc = TaskService(Database(DB_PATH))
    result = svc.delete(task_id=task_id)

@cli.command('task-show')
def task_show():
    """task/show"""
    svc = TaskService(Database(DB_PATH))
    result = svc.list()


if __name__ == "__main__":
    cli()

