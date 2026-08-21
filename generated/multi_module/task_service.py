"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from models import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def create_task(self, title: str, description: Optional[str] = None, status: str = None) -> Task:
        task = Task(title=title, description=description, status=status, created_at=datetime.datetime.now().isoformat())
        return self.task_repo.create(task)

    def update_task(self, task_id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None) -> Optional[Task]:
        data = {k: v for k, v in {'title': title, 'description': description, 'status': status}.items() if v is not None}
        return self.task_repo.update(task_id, data)

    def list_tasks(self, status: Optional[str] = None, page: int = None, page_size: int = None) -> List[Task]:
        return self.task_repo.list()

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        return self.task_repo.get_by_id(task_id)

    def delete_task(self, task_id: int) -> bool:
        return self.task_repo.delete(task_id)

