"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from database import Database
from exceptions import (
    ValidationError,
)
from models import Project, Task
from project_repository import ProjectRepository
from task_repository import TaskRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.task_repo = TaskRepository(db)

    def create_project(self, title: str, description: Optional[str] = None) -> int:
        project = Project(title=title, description=description, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.project_repo.create(project)

    def update_project(self, project_id: int, title: Optional[str] = None, description: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'title': title, 'description': description}.items() if v is not None}
        return self.project_repo.update(project_id, data)

    def delete_project(self, project_id: int) -> bool:
        return self.project_repo.delete(project_id)

    def list_projects(self) -> List[Dict[str, Any]]:
        results = {}
        for row in self.project_repo.list():
            key = row.title
            results[key] = results.get(key, 0) + row.id
        return results

    def get_project_tasks_summary(self, project_id: int, status_filter: Optional[str] = None, priority_filter: Optional[int] = None) -> Dict[str, Any]:
        rows = self.task_repo.list(project_id=project_id)
        total = sum(e.id for e in rows)
        return {'task_count_filtered': total}

    def search_tasks_by_title(self, query: str, project_id: int) -> List[Dict[str, Any]]:
        """
            Search tasks by title within a specific project.
        
            Args:
                query: The search query string to match against task titles.
                project_id: The ID of the project to search within.
            
            Returns:
                A list of dictionaries containing task details that match the query and belong to the project.
            """
        if not query or not isinstance(query, str):
            raise ValidationError('Query must be a non-empty string.')
        if not isinstance(project_id, int):
            raise ValidationError('Project ID must be an integer.')
        results = self.task_repo.search_tasks_by_title_and_project(query, project_id)
        task_list = []
        for task in results:
            task_dict = {'id': task.id, 'title': task.title, 'description': task.description, 'priority': task.priority, 'status': task.status, 'project_id': task.project_id, 'created_at': task.created_at.isoformat() if task.created_at else None, 'updated_at': task.updated_at.isoformat() if task.updated_at else None}
            task_list.append(task_dict)
        return task_list

    def get_project_completion_rate(self, project_id: int) -> float:
        raise NotImplementedError()

    def get_task_stats_by_project(self) -> Dict[str, Any]:
        results = {}
        for row in self.task_repo.list():
            key = row.project_id
            results[key] = results.get(key, 0) + row.priority
        return results

    def list_tasks_by_status_and_priority(self, status: str, priority: int) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.task_repo.list(status=status, priority=priority):
            key = (row.status, row.priority)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'status': key[0],
                    'priority': key[1],
                    'count': len(group),
                })
        return results

    def get_total_tasks_by_status(self) -> Dict[str, int]:
        raise NotImplementedError()

    def get_project_task_distribution(self) -> Dict[str, int]:
        results = {}
        for row in self.task_repo.list():
            key = row.project_id
            results[key] = results.get(key, 0) + row.id
        return results

    def list_task(self, project_id: int, status: str, priority: int) -> List[Task]:
        return self.task_repo.list(project_id=project_id, status=status, priority=priority)

