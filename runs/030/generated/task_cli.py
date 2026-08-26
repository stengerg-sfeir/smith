import sqlite3

import click


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None

    def get_connection(self):
        if self.connection is None:
            self.connection = sqlite3.connect(self.db_path)
        return self.connection

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class TaskService:
    def __init__(self, db: Database):
        self.db = db

    def get_tasks_by_status_and_priority(self, status: str, priority: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE status = ? AND priority = ?", (status, priority))
        rows = cursor.fetchall()
        return rows

    def get_tasks_by_user_id(self, user_id: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        return rows

    def get_tasks_with_due_date_range(self, start_date: str, end_date: str):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE due_date BETWEEN ? AND ?",
            (start_date, end_date)
        )
        rows = cursor.fetchall()
        return rows

    def get_overdue_tasks(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE due_date < CURRENT_DATE")
        rows = cursor.fetchall()
        return rows

    def get_tasks_with_high_priority_and_due_soon(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE priority > 5 AND due_date BETWEEN DATE('now', 'start of day') AND DATE('now', 'start of day', '+1 day')"
        )
        rows = cursor.fetchall()
        return rows

    def get_tasks_with_status_and_created_range(self, status: str, start_created: str, end_created: str):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE status = ? AND created_at BETWEEN ? AND ?",
            (status, start_created, end_created)
        )
        rows = cursor.fetchall()
        return rows

    def get_summary_by_status_and_priority(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, priority, COUNT(*) as count
            FROM tasks
            GROUP BY status, priority
        """)
        rows = cursor.fetchall()
        return rows

    def get_task_count_by_status(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) as count FROM tasks GROUP BY status")
        rows = cursor.fetchall()
        return rows

    def get_tasks_below_priority_threshold(self, threshold_priority: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE priority < ?", (threshold_priority,))
        rows = cursor.fetchall()
        return rows

    def close(self):
        self.db.close()


DB_PATH = "app.db"


@click.group()
def cli():
    """Application root."""


@cli.command('query-by_status_and_priority')
@click.option('--status', required=True)
@click.option('--priority', type=int, required=True)
def query_by_status_and_priority(status, priority):
    """tasks/query/by_status_and_priority"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_by_status_and_priority(status=status, priority=priority)
    click.echo(str(result))


@cli.command('query-by_user_id')
@click.option('--user-id', type=int, required=True)
def query_by_user_id(user_id):
    """tasks/query/by_user_id"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_by_user_id(user_id=user_id)
    click.echo(str(result))


@cli.command('query-due_date_range')
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def query_due_date_range(start_date, end_date):
    """tasks/query/due_date_range"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_with_due_date_range(start_date=start_date, end_date=end_date)
    click.echo(str(result))


@cli.command('query-overdue')
def query_overdue():
    """tasks/query/overdue"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_overdue_tasks()
    click.echo(str(result))


@cli.command('query-high_priority_due_soon')
def query_high_priority_due_soon():
    """tasks/query/high_priority_due_soon"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_with_high_priority_and_due_soon()
    click.echo(str(result))


@cli.command('query-status_created_range')
@click.option('--status', required=True)
@click.option('--start-created', required=True)
@click.option('--end-created', required=True)
def query_status_created_range(status, start_created, end_created):
    """tasks/query/status_created_range"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_with_status_and_created_range(status=status, start_created=start_created, end_created=end_created)
    click.echo(str(result))


@cli.command('report-summary_by_status_priority')
def report_summary_by_status_priority():
    """tasks/report/summary_by_status_priority"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_summary_by_status_and_priority()
    click.echo(str(result))


@cli.command('report-count_by_status')
def report_count_by_status():
    """tasks/report/count_by_status"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_task_count_by_status()
    click.echo(str(result))


@cli.command('report-below_priority_threshold')
@click.option('--threshold', type=int, required=True)
def report_below_priority_threshold(threshold):
    """tasks/report/below_priority_threshold"""
    svc = TaskService(Database(DB_PATH))
    result = svc.get_tasks_below_priority_threshold(threshold_priority=threshold)
    click.echo(str(result))


@cli.command('export-export_csv')
@click.option('--file-path', required=True)
@click.option('--filter-status')
@click.option('--filter-priority', type=int)
def export_export_csv(file_path, filter_status, filter_priority):
    """tasks/export/export_csv"""
    svc = TaskService(Database(DB_PATH))
    # Placeholder for CSV export logic
    click.echo(f"Exporting to {file_path} with filter_status={filter_status}, filter_priority={filter_priority}")
