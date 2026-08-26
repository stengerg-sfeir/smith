import click
from database import Database
from task_service import TaskService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('list-by_status_and_priority')
@click.option('--status', required=True)
@click.option('--priority', type=int, required=True)
def list_by_status_and_priority(status, priority):
    """task/list/by_status_and_priority"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_by_status_and_priority(status=status, priority=priority)

@cli.command('list-by_user_id')
@click.option('--user-id', type=int, required=True)
def list_by_user_id(user_id):
    """task/list/by_user_id"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_by_user_id(user_id=user_id)

@cli.command('list-by_due_date_range')
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def list_by_due_date_range(start_date, end_date):
    """task/list/by_due_date_range"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_with_due_date_range(start_date=start_date, end_date=end_date)

@cli.command('list-overdue')
def list_overdue():
    """task/list/overdue"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_overdue_tasks()

@cli.command('list-high_priority_due_soon')
def list_high_priority_due_soon():
    """task/list/high_priority_due_soon"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_with_high_priority_and_due_soon()

@cli.command('list-by_status_and_created_range')
@click.option('--status', required=True)
@click.option('--start-created', required=True)
@click.option('--end-created', required=True)
def list_by_status_and_created_range(status, start_created, end_created):
    """task/list/by_status_and_created_range"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_with_status_and_created_range(status=status, start_created=start_created, end_created=end_created)

@cli.command('stats-count_by_status')
def stats_count_by_status():
    """task/stats/count_by_status"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_task_count_by_status()

@cli.command('stats-priority_by_status')
def stats_priority_by_status():
    """task/stats/priority_by_status"""
    svc = TaskService(Database(DB_PATH))
    result = svc.sum_task_priority_by_status()

@cli.command('export-to_csv')
@click.option('--file-path', required=True)
@click.option('--filter-status')
@click.option('--filter-priority', type=int)
def export_to_csv(file_path, filter_status, filter_priority):
    """task/export/to_csv"""
    svc = TaskService(Database(DB_PATH))
    result = svc.export_tasks_to_csv(file_path=file_path, filter_status=filter_status, filter_priority=filter_priority)

@cli.command('analyze-duplicates_by_title')
def analyze_duplicates_by_title():
    """task/analyze/duplicates_by_title"""
    svc = TaskService(Database(DB_PATH))
    result = svc.find_duplicate_tasks_by_title()

@cli.command('filter-below_priority_threshold')
@click.option('--user-id', type=int, required=True)
def filter_below_priority_threshold(user_id):
    """task/filter/below_priority_threshold"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_below_user_priority_threshold(user_id=user_id)


if __name__ == "__main__":
    cli()

