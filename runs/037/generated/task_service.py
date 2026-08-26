"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from exceptions import (
    ProjectNotFoundError,
)
from models import Task
from project_repository import ProjectRepository
from task_repository import TaskRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.task_repo = TaskRepository(db)

    def create_task(self, project_id: int, title: str, description: Optional[str] = None, status: str = None, priority: int = None, due_date: Optional[date] = None) -> Task:
        if project_id is not None:
            if self.project_repo.get_by_id(project_id) is None:
                raise ProjectNotFoundError(project_id)
        task = Task(project_id=project_id, title=title, description=description, status=status, priority=priority, due_date=due_date, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.task_repo.create(task)

    def update_task(self, task_id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None, priority: Optional[int] = None, due_date: Optional[date] = None) -> Task:
        data = {k: v for k, v in {'title': title, 'description': description, 'status': status, 'priority': priority, 'due_date': due_date}.items() if v is not None}
        return self.task_repo.update(task_id, data)

    def delete_task(self, task_id: int) -> bool:
        return self.task_repo.delete(task_id)

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        return self.task_repo.get_by_id(task_id)

    def list_tasks_by_project(self, project_id: int, status_filter: Optional[str]=None, priority_filter: Optional[int]=None, due_date_range: Optional[tuple[datetime.datetime, datetime.datetime]]=None) -> list[Task]:
        """
            Retrieves tasks for a specific project with optional filters on status, priority, and due date range.
            """
        try:
            self.project_repo.get_by_id(project_id)
        except ProjectNotFoundError:
            raise ProjectNotFoundError(f'Project with id {project_id} not found')
        filters = {}
        if status_filter is not None:
            filters['status'] = status_filter
        if priority_filter is not None:
            filters['priority'] = priority_filter
        if due_date_range is not None:
            filters['due_date_range'] = due_date_range
        return self.task_repo.list_tasks_by_project(project_id=project_id, status_filter=status_filter, priority_filter=priority_filter, due_date_range=due_date_range)

    def get_task_stats_by_status(self) -> dict[str, int]:
        results = {}
        for row in self.task_repo.list():
            key = row.status
            results[key] = results.get(key, 0) + row.priority
        return results

    def get_task_completion_rate(self, project_id: int) -> float:
        """
            Returns the completion rate of tasks for a given project.
            Completion rate = (completed tasks / total tasks) * 100
            """
        try:
            project = self.project_repo.get_by_id(project_id)
        except ProjectNotFoundError:
            raise ProjectNotFoundError(f'Project with id {project_id} not found')
        total_tasks = self.task_repo.get_project_task_count(project_id)
        if total_tasks == 0:
            return 0.0
        completion_rate = self.task_repo.get_task_completion_rate(project_id)
        return completion_rate

    def get_tasks_with_overdue_due_dates(self) -> list[Task]:
        """
            Retrieves all tasks with overdue due dates.
            """
        return self.task_repo.get_tasks_with_overdue_due_dates()

    def get_tasks_by_priority_and_status(self, status: str, priority: int) -> list[Task]:
        """
            Retrieves tasks filtered by status and priority.
            """
        return self.task_repo.get_tasks_by_priority_and_status(status=status, priority=priority)

    def get_project_task_count(self, project_id: int) -> int:
        rows = self.task_repo.list(project_id=project_id)
        return sum(e.priority for e in rows)

    def search_tasks_by_title(self, query: str, limit: int) -> list[Task]:
        """
            Searches tasks by title using a query string and returns up to 'limit' results.
            """
        return self.task_repo.search_tasks_by_title(query=query, limit=limit)

