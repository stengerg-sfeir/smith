"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

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

    def create_task(self, project_id: int, title: str, description: Optional[str] = None, status: str = None, priority: int = None) -> bool:
        if project_id is not None:
            if self.project_repo.get_by_id(project_id) is None:
                raise ProjectNotFoundError(project_id)
        task = Task(project_id=project_id, title=title, description=description, status=status, priority=priority, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.task_repo.create(task)

    def update_task(self, task_id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None, priority: Optional[int] = None) -> bool:
        data = {k: v for k, v in {'title': title, 'description': description, 'status': status, 'priority': priority}.items() if v is not None}
        return self.task_repo.update(task_id, data)

    def delete_task(self, task_id: int) -> bool:
        return self.task_repo.delete(task_id)

    def list_tasks(self, project_id: Optional[int] = None, status: Optional[str] = None, priority: Optional[int] = None) -> List[Dict[str, Any]]:
        results = {}
        for row in self.task_repo.list(project_id=project_id, status=status, priority=priority):
            key = (row.status, row.priority)
            results[key] = results.get(key, 0) + row.priority
        return results

    def search_tasks(self, query: str, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError()

    def get_task_stats_by_project(self) -> Dict[str, Any]:
        """Retrieve task statistics grouped by project."""
        project_task_stats = {}
        projects_with_tasks = self.project_repo.get_project_with_tasks(project_id=None)
        projects = self.project_repo.list_projects_with_task_count()
        for project in projects:
            project_id = project['id']
            task_stats = self.task_repo.get_tasks_by_status_and_priority_with_project_info(status=None, priority=None)
            project_tasks = self.task_repo.get_tasks_by_project_and_status(project_id=project_id, status=None)
            status_priority_count = {}
            for task in project_tasks:
                status = task['status']
                priority = task['priority']
                key = (status, priority)
                status_priority_count[key] = status_priority_count.get(key, 0) + 1
            project_task_stats[project_id] = {'total_tasks': len(project_tasks), 'task_distribution': status_priority_count}
        return project_task_stats

