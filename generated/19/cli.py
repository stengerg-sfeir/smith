import click
from database import Database
from task_service import TaskService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('task-add')
@click.option('--title', required=True)
@click.option('--description')
@click.option('--status', required=True)
@click.option('--priority', required=True)
@click.option('--due-date')
def task_add(title, description, status, priority, due_date):
    """task/add"""
    svc = TaskService(Database(DB_PATH))
    result = svc.add_task(title=title, description=description, status=status, priority=priority, due_date=due_date)

@cli.command('task-list')
@click.option('--title')
@click.option('--status')
@click.option('--priority')
@click.option('--due-date')
@click.option('--due-date-end')
def task_list(title, status, priority, due_date, due_date_end):
    """task/list"""
    svc = TaskService(Database(DB_PATH))
    result = svc.list_task(title=title, status=status, priority=priority, due_date=due_date, due_date_end=due_date_end)

@cli.command('task-update')
@click.option('--id', type=int, required=True)
@click.option('--title')
@click.option('--description')
@click.option('--status')
@click.option('--priority')
@click.option('--due-date')
def task_update(id, title, description, status, priority, due_date):
    """task/update"""
    svc = TaskService(Database(DB_PATH))
    result = svc.update_task(id=id, title=title, description=description, status=status, priority=priority, due_date=due_date)

@cli.command('task-delete')
@click.option('--id', type=int, required=True)
def task_delete(id):
    """task/delete"""
    svc = TaskService(Database(DB_PATH))
    result = svc.delete_task(id=id)

@cli.command('task-import')
@click.option('--id', type=int, required=True)
def task_import(id):
    """task/import"""
    svc = TaskService(Database(DB_PATH))
    result = svc.import_task(id=id)


if __name__ == "__main__":
    cli()

