"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from exceptions import (
    ProjectNotFoundError,
)
from models import Project
from project_repository import ProjectRepository
from task_repository import TaskRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.task_repo = TaskRepository(db)

    def create_project(self, name: str, description: Optional[str] = None) -> int:
        project = Project(name=name, description=description, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.project_repo.create(project)

    def get_project_with_tasks(self, project_id: int) -> Optional[ProjectWithTasks]:
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)
        tasks = self.task_repo.list_tasks_by_project(project_id=project_id, status_filter=None, priority_filter=None, due_date_range=None)
        return ProjectWithTasks(project=project, tasks=tasks)

    def list_projects_with_task_count(self, status_filter: Optional[str]=None, priority_filter: Optional[int]=None, due_date_range: Optional[tuple[datetime.datetime, datetime.datetime]]=None) -> list[ProjectWithTaskCount]:
        return self.project_repo.list_projects_with_task_count(status_filter=status_filter, priority_filter=priority_filter, due_date_range=due_date_range)

    def get_project_tasks_summary(self, project_id: int) -> dict[str, int]:
        results = {}
        for row in self.task_repo.list(project_id=project_id):
            key = row.status
            results[key] = results.get(key, 0) + row.id
        return results

    def get_overdue_tasks_count_by_project(self) -> dict[int, int]:
        results = {}
        for row in self.task_repo.list():
            key = row.project_id
            results[key] = results.get(key, 0) + row.id
        return results

    def get_project_completion_rate(self, project_id: int) -> float:
        rows = self.task_repo.list(project_id=project_id)
        return sum(e.id for e in rows)

    def search_projects_by_name(self, query: str, limit: int) -> list[Project]:
        return self.project_repo.search_projects_by_name(query=query, limit=limit)

    def delete_project(self, project_id: int) -> bool:
        return self.project_repo.delete(project_id)

    def get_project_creation_trend(self, start_date: datetime.datetime, end_date: datetime.datetime, interval: str) -> dict[str, int]:
        return self.project_repo.get_project_creation_trend(start_date=start_date, end_date=end_date, interval=interval)

