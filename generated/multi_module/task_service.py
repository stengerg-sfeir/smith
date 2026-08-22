"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Dict, List, Optional

from database import Database
from models import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def create_task(self, title: str, description: Optional[str] = None, status: str = None) -> Optional[Task]:
        task = Task(title=title, description=description, status=status, created_at=datetime.datetime.now().isoformat())
        return self.task_repo.create(task)

    def update_task(self, task_id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None) -> Optional[Task]:
        data = {k: v for k, v in {'title': title, 'description': description, 'status': status}.items() if v is not None}
        return self.task_repo.update(task_id, data)

    def list_tasks(self, status: Optional[str] = None, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Task]:
        return self.task_repo.list(status=status)

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        return self.task_repo.get_by_id(task_id)

    def delete_task(self, task_id: int) -> bool:
        return self.task_repo.delete(task_id)

    def get_status_distribution(self) -> Dict[str, int]:
        """Returns a dictionary with the count of tasks by status."""
        return self.task_repo.get_tasks_with_status_distribution()

    def export_tasks_to_csv(self, file_path: str, status_filter: Optional[str] = None) -> None:
        rows = self.task_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'title', 'description', 'status',
                'created_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.title, row.description, row.status,
                    row.created_at,
                ])

