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

    def search_tasks(self, query: str, project_id: Optional[int]=None) -> List[Dict[str, Any]]:
        """
            Search for tasks by title, optionally filtered by project_id.
        
            Args:
                query: Search query string to match against task titles
                project_id: Optional project ID to filter tasks by project
            
            Returns:
                List of dictionaries containing task data matching the query
            """
        if project_id is not None:
            return self.task_repo.search_tasks_by_title_and_project(query, project_id)
        else:
            return self.task_repo.search_tasks_by_title(query, project_id)

    def get_task_stats_by_project(self) -> Dict[str, Any]:
        """
            Retrieves task statistics grouped by project.
            Returns a dictionary with project titles as keys and task statistics as values.
            """
        projects_with_tasks = self.project_repo.list_projects_with_task_count()
        result = {}
        for project in projects_with_tasks:
            project_id = project['id']
            project_title = project['title']
            task_stats = self.task_repo.get_tasks_by_status_and_priority_with_project_info(status=None, priority=None)
            filtered_tasks = [task for task in task_stats if task.get('project_id') == project_id]
            task_summary = {'completed_tasks': 0, 'in_progress_tasks': 0, 'pending_tasks': 0, 'total_tasks': 0, 'status_distribution': {}, 'priority_distribution': {}}
            for task in filtered_tasks:
                status = task.get('status')
                priority = task.get('priority')
                if status == 'completed':
                    task_summary['completed_tasks'] += 1
                elif status == 'in_progress':
                    task_summary['in_progress_tasks'] += 1
                elif status == 'pending':
                    task_summary['pending_tasks'] += 1
                if priority not in task_summary['priority_distribution']:
                    task_summary['priority_distribution'][priority] = 0
                task_summary['priority_distribution'][priority] += 1
                task_summary['total_tasks'] += 1
            result[project_title] = task_summary
        return result

