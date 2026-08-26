import click
from database import Database
from project_service import ProjectService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('project-create')
@click.option('--title', required=True)
@click.option('--description')
def project_create(title, description):
    """project/create"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.create_project(title=title, description=description)

@cli.command('project-list')
def project_list():
    """project/list"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_projects()

@cli.command('project-update')
@click.option('--project-id', type=int, required=True)
@click.option('--title')
@click.option('--description')
def project_update(project_id, title, description):
    """project/update"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.update_project(project_id=project_id, title=title, description=description)

@cli.command('project-delete')
@click.option('--project-id', type=int, required=True)
def project_delete(project_id):
    """project/delete"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.delete_project(project_id=project_id)

@cli.command('task-list')
@click.option('--project-id', type=int)
@click.option('--status')
@click.option('--priority', type=int)
def task_list(project_id, status, priority):
    """task/list"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.list_task(project_id=project_id, status=status, priority=priority)

@cli.command('task-search')
@click.option('--query', required=True)
@click.option('--project-id', type=int)
def task_search(query, project_id):
    """task/search"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.search_tasks_by_title(query=query, project_id=project_id)

@cli.command('project-summary')
@click.option('--project-id', type=int, required=True)
@click.option('--status-filter')
@click.option('--priority-filter', type=int)
def project_summary(project_id, status_filter, priority_filter):
    """project/summary"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_tasks_summary(project_id=project_id, status_filter=status_filter, priority_filter=priority_filter)

@cli.command('project-stats')
def project_stats():
    """project/stats"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_task_stats_by_project()

@cli.command('project-completion_rate')
@click.option('--project-id', type=int, required=True)
def project_completion_rate(project_id):
    """project/completion_rate"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_completion_rate(project_id=project_id)

@cli.command('project-task_distribution')
def project_task_distribution():
    """project/task_distribution"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_project_task_distribution()

@cli.command('project-total_status')
def project_total_status():
    """project/total_status"""
    svc = ProjectService(Database(DB_PATH))
    result = svc.get_total_tasks_by_status()


if __name__ == "__main__":
    cli()

