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
def project_create(name, description):
    """project/create"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.create_project(name=name, description=description)

@cli.command('project-delete')
@click.option('--id', type=int, required=True)
def project_delete(id):
    """project/delete"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.delete_project(project_id=id)

@cli.command('project-list')
@click.option('--status-filter')
@click.option('--priority-filter', type=int)
@click.option('--due-date-range')
def project_list(status_filter, priority_filter, due_date_range):
    """project/list"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_projects_with_task_count(status_filter=status_filter, priority_filter=priority_filter, due_date_range=due_date_range)

@cli.command('project-get_tasks_summary')
@click.option('--project-id', type=int, required=True)
def project_get_tasks_summary(project_id):
    """project/get_tasks_summary"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_tasks_summary(project_id=project_id)

@cli.command('project-get_overdue_tasks')
def project_get_overdue_tasks():
    """project/get_overdue_tasks"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_overdue_tasks_count_by_project()

@cli.command('project-get_completion_rate')
@click.option('--project-id', type=int, required=True)
def project_get_completion_rate(project_id):
    """project/get_completion_rate"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_completion_rate(project_id=project_id)

@cli.command('project-get_trend')
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
@click.option('--interval', required=True)
def project_get_trend(start_date, end_date, interval):
    """project/get_trend"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_creation_trend(start_date=start_date, end_date=end_date, interval=interval)

@cli.command('project-get_with_tasks')
@click.option('--id', type=int, required=True)
def project_get_with_tasks(id):
    """project/get_with_tasks"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_with_tasks(project_id=id)

@cli.command('project-search')
@click.option('--query', required=True)
@click.option('--limit', type=int)
def project_search(query, limit):
    """project/search"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.search_projects_by_name(query=query, limit=limit)


if __name__ == "__main__":
    cli()

