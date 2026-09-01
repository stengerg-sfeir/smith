import click
from database import Database
from task_service import TaskService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('manage-add')
@click.option('--title', required=True)
@click.option('--description')
@click.option('--status', required=True)
@click.option('--priority', type=int, required=True)
@click.option('--due-date')
def manage_add(title, description, status, priority, due_date):
    """task/manage/add"""
    svc = TaskService(Database(DB_PATH))
    result = svc.add(title=title, description=description, status=status, priority=priority, due_date=due_date)

@cli.command('manage-list')
@click.option('--status')
@click.option('--priority', type=int)
@click.option('--page', type=int)
@click.option('--page-size', type=int)
def manage_list(status, priority, page, page_size):
    """task/manage/list"""
    svc = TaskService(Database(DB_PATH))
    result = svc.list(status=status, priority=priority, page=page, page_size=page_size)

@cli.command('manage-update')
@click.option('--task-id', type=int, required=True)
@click.option('--title')
@click.option('--description')
@click.option('--status')
@click.option('--priority', type=int)
@click.option('--due-date')
def manage_update(task_id, title, description, status, priority, due_date):
    """task/manage/update"""
    svc = TaskService(Database(DB_PATH))
    result = svc.update(task_id=task_id, title=title, description=description, status=status, priority=priority, due_date=due_date)

@cli.command('manage-delete')
@click.option('--task-id', type=int, required=True)
def manage_delete(task_id):
    """task/manage/delete"""
    svc = TaskService(Database(DB_PATH))
    result = svc.delete(task_id=task_id)


if __name__ == "__main__":
    cli()

