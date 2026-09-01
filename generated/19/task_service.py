"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from database import Database
from exceptions import ImportError, NotFoundError, ValidationException
from models import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def add_task(self, title: str, description: Optional[str] = None, status: str = None, priority: str = None, due_date: Optional[str] = None) -> bool:
        task = Task(title=title, description=description, status=status, priority=priority, due_date=due_date, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.task_repo.create(task)

    def list_task(self, title: Optional[str] = None, status: Optional[str] = None, priority: Optional[str] = None, due_date: Optional[str] = None, due_date_end: Optional[str] = None) -> list[Task]:
        return self.task_repo.list(title=title, status=status, priority=priority, due_date=due_date, due_date_end=due_date_end)

    def update_task(self, id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None, priority: Optional[str] = None, due_date: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'title': title, 'description': description, 'status': status, 'priority': priority, 'due_date': due_date}.items() if v is not None}
        return self.task_repo.update(id, data)

    def delete_task(self, id: int) -> bool:
        return self.task_repo.delete(id)

    def report(self, id: int) -> dict[str, Any]:
        """
            Generate a detailed report for a specific task by ID.
            """
        try:
            task = self.task_repo.get_by_id(id)
            if not task:
                raise NotFoundError(f'Task with id {id} not found')
            report = {'id': task.id, 'title': task.title, 'description': task.description, 'status': task.status, 'priority': task.priority, 'due_date': task.due_date.isoformat() if task.due_date else None, 'created_at': task.created_at.isoformat(), 'updated_at': task.updated_at.isoformat()}
            status_count = self.task_repo.get_task_count_by_status()
            priority_status_summary = self.task_repo.get_tasks_with_priority_and_status_summary()
            report['task_count_by_status'] = status_count
            report['priority_status_summary'] = priority_status_summary
            return report
        except Exception as e:
            raise NotFoundError(f'Task with id {id} not found') from e

    def import_task(self, json_data: Dict[str, Any]) -> bool:
        """
            Import tasks from JSON data.
            Returns True if import was successful, False otherwise.
            """
        try:
            if not isinstance(json_data, dict):
                raise ValidationException('Invalid JSON data: must be a dictionary')
            return self.task_repo.import_tasks_from_json(json_data)
        except Exception as e:
            raise ImportError(f'Failed to import tasks: {str(e)}') from e

