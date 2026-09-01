"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from exceptions import (
    InvalidStatusError,
    ValidationError,
)
from models import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def add(self, title: str, description: Optional[str]=None, status: str=None) -> None:
        if status and status not in ['todo', 'in_progress', 'completed']:
            raise InvalidStatusError(f'Invalid status: {status}')
        task = Task(created_at=datetime.datetime.now(), description=description, id=None, status=status or 'todo', title=title)
        self.task_repo.create(task)

    def list(self, status: Optional[str]=None, limit: Optional[int]=None, offset: Optional[int]=None) -> List[Task]:
        filters = {}
        if status is not None:
            filters['status'] = status
        if limit is not None:
            filters['limit'] = limit
        if offset is not None:
            filters['offset'] = offset
        return self.task_repo.list(**filters)

    def update(self, task_id: int, title: Optional[str]=None, description: Optional[str]=None, status: Optional[str]=None) -> None:
        if status and status not in ['todo', 'in_progress', 'completed']:
            raise InvalidStatusError(f'Invalid status: {status}')
        update_data = {}
        if title is not None:
            update_data['title'] = title
        if description is not None:
            update_data['description'] = description
        if status is not None:
            update_data['status'] = status
        if not update_data:
            raise ValidationError('No valid fields provided for update')
        self.task_repo.update(task_id, update_data)

    def delete(self, task_id: int) -> None:
        self.task_repo.delete(task_id)

