import click
from database import Database
from task_service import TaskService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('task-count')
def task_count():
    """task/count"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_task_count_by_status()

@cli.command('task-create')
@click.option('--title', required=True)
@click.option('--description')
@click.option('--status')
@click.option('--priority')
@click.option('--due-date')
def task_create(title, description, status, priority, due_date):
    """task/create"""
    svc = TaskService(Database(DB_PATH))
    result = svc.create_task(title=title, description=description, status=status, priority=priority, due_date=due_date)

@cli.command('task-update')
@click.option('--task-id', type=int, required=True)
@click.option('--title')
@click.option('--description')
@click.option('--status')
@click.option('--priority')
@click.option('--due-date')
def task_update(task_id, title, description, status, priority, due_date):
    """task/update"""
    svc = TaskService(Database(DB_PATH))
    result = svc.update_task(task_id=task_id, title=title, description=description, status=status, priority=priority, due_date=due_date)

@cli.command('task-delete')
@click.option('--task-id', type=int, required=True)
def task_delete(task_id):
    """task/delete"""
    svc = TaskService(Database(DB_PATH))
    result = svc.delete_task(task_id=task_id)

@cli.command('task-export')
def task_export():
    """task/export"""
    svc = TaskService(Database(DB_PATH))
    result = svc.export_tasks_to_json()

@cli.command('task-import')
@click.option('--json-file', required=True)
def task_import(json_file):
    """task/import"""
    svc = TaskService(Database(DB_PATH))
    result = svc.import_tasks_from_json(json_data=json_file)

@cli.command('task-overdue')
def task_overdue():
    """task/overdue"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_overdue_tasks()


if __name__ == "__main__":
    cli()

