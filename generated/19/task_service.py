"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from database import Database
from exceptions import ExportError, ImportError
from models import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def create_task(self, title: str, description: Optional[str] = None, status: str = None, priority: str = None, due_date: Optional[date] = None) -> bool:
        task = Task(title=title, description=description, status=status, priority=priority, due_date=due_date, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.task_repo.create(task)

    def update_task(self, task_id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None, priority: Optional[str] = None, due_date: Optional[date] = None) -> bool:
        data = {k: v for k, v in {'title': title, 'description': description, 'status': status, 'priority': priority, 'due_date': due_date}.items() if v is not None}
        return self.task_repo.update(task_id, data)

    def delete_task(self, task_id: int) -> bool:
        return self.task_repo.delete(task_id)

    def get_tasks_by_status_and_priority(self, status: str, priority: str) -> List[Task]:
        return self.task_repo.get_tasks_by_status_and_priority(status, priority)

    def get_tasks_with_due_date_range(self, start_date: date, end_date: date) -> List[Task]:
        return self.task_repo.get_tasks_with_due_date_range(start_date, end_date)

    def get_task_count_by_status(self) -> Dict[str, int]:
        return self.task_repo.get_task_count_by_status()

    def get_tasks_with_pagination(self, page: int, page_size: int) -> List[Task]:
        return self.task_repo.get_tasks_with_pagination(page, page_size)

    def export_tasks_to_json(self) -> str:
        try:
            return self.task_repo.export_tasks_to_json()
        except Exception as e:
            raise ExportError(f'Failed to export tasks: {str(e)}')

    def import_tasks_from_json(self, json_data: str) -> bool:
        try:
            return self.task_repo.import_tasks_from_json(json_data)
        except Exception as e:
            raise ImportError(f'Failed to import tasks: {str(e)}')

    def get_overdue_tasks(self) -> List[Task]:
        return self.task_repo.get_overdue_tasks()

    def get_tasks_by_user(self, user_id: int) -> List[Task]:
        return self.task_repo.get_tasks_by_user(user_id)

