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
def manage_add(title, description, status):
    """task/manage/add"""
    svc = TaskService(Database(DB_PATH))
    result = svc.create_task(title=title, description=description, status=status)

@cli.command('manage-list')
@click.option('--status')
@click.option('--limit', type=int)
@click.option('--offset', type=int)
def manage_list(status, limit, offset):
    """task/manage/list"""
    svc = TaskService(Database(DB_PATH))
    result = svc.list_tasks(status=status, limit=limit, offset=offset)

@cli.command('manage-update')
@click.option('--title')
@click.option('--description')
@click.option('--status')
@click.option('--task-id', type=int, required=True)
def manage_update(title, description, status, task_id):
    """task/manage/update"""
    svc = TaskService(Database(DB_PATH))
    result = svc.update_task(title=title, description=description, status=status, task_id=task_id)

@cli.command('manage-delete')
@click.option('--task-id', type=int, required=True)
def manage_delete(task_id):
    """task/manage/delete"""
    svc = TaskService(Database(DB_PATH))
    result = svc.delete_task(task_id=task_id)

@cli.command('view-show')
@click.option('--task-id', type=int, required=True)
def view_show(task_id):
    """task/view/show"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_task_by_id(task_id=task_id)

@cli.command('report-status_distribution')
def report_status_distribution():
    """task/report/status_distribution"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_status_distribution()

@cli.command('task-export')
@click.option('--file-path', required=True)
@click.option('--status-filter')
def task_export(file_path, status_filter):
    """task/export"""
    svc = TaskService(Database(DB_PATH))
    result = svc.export_tasks_to_csv(file_path=file_path, status_filter=status_filter)


if __name__ == "__main__":
    cli()

