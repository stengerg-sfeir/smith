"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from exceptions import (
    NotFoundError,
    TaskAlreadyExistsError,
    TaskNotFoundException,
    ValidationException,
)
from models import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def add(self, title: str, description: Optional[str]=None, status: str=None, priority: int=None, due_date: Optional[str]=None) -> bool:
        try:
            if not title or not isinstance(title, str):
                raise ValidationException('Title is required and must be a string.')
            if priority is not None and (priority < 1 or priority > 5):
                raise ValidationException('Priority must be an integer between 1 and 5.')
            if due_date is not None and (not self._is_valid_date(due_date)):
                raise ValidationException('Due date must be in YYYY-MM-DD format.')
            task = Task(created_at=datetime.datetime.now().isoformat(), description=description or '', due_date=due_date, id=None, priority=priority or 3, status=status or 'pending', title=title, updated_at=datetime.datetime.now().isoformat())
            self.task_repo.create(task)
            return True
        except Exception as e:
            if isinstance(e, TaskAlreadyExistsError):
                raise e
            raise ValidationException(f'Failed to add task: {str(e)}')

    def list(self, status: Optional[str]=None, priority: Optional[int]=None, page: int=None, page_size: int=None) -> list[Task]:
        try:
            filters = {}
            if status is not None:
                filters['status'] = status
            if priority is not None:
                filters['priority'] = priority
            if page is not None and page_size is not None:
                return self.task_repo.get_tasks_with_pagination(page, page_size)
            return self.task_repo.list(**filters)
        except Exception as e:
            raise NotFoundError(f'Failed to list tasks: {str(e)}')

    def update(self, task_id: int, title: Optional[str]=None, description: Optional[str]=None, status: Optional[str]=None, priority: Optional[int]=None, due_date: Optional[str]=None) -> bool:
        try:
            if not isinstance(task_id, int) or task_id <= 0:
                raise ValidationException('Task ID must be a positive integer.')
            update_data = {}
            if title is not None:
                update_data['title'] = title
            if description is not None:
                update_data['description'] = description
            if status is not None:
                update_data['status'] = status
            if priority is not None and (priority < 1 or priority > 5):
                raise ValidationException('Priority must be an integer between 1 and 5.')
            if due_date is not None and (not self._is_valid_date(due_date)):
                raise ValidationException('Due date must be in YYYY-MM-DD format.')
            if due_date is not None:
                update_data['due_date'] = due_date
            self.task_repo.update(task_id, update_data)
            return True
        except Exception as e:
            if isinstance(e, TaskNotFoundException):
                raise e
            raise ValidationException(f'Failed to update task: {str(e)}')

    def delete(self, task_id: int) -> bool:
        try:
            if not isinstance(task_id, int) or task_id <= 0:
                raise ValidationException('Task ID must be a positive integer.')
            self.task_repo.delete(task_id)
            return True
        except Exception as e:
            if isinstance(e, TaskNotFoundException):
                raise e
            raise ValidationException(f'Failed to delete task: {str(e)}')

