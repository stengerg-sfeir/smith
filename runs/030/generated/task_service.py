"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Dict, List, Optional

from database import Database
from task import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def get_tasks_by_status_and_priority(self, status: str, priority: int) -> List[Task]:
        return self.task_repo.get_tasks_by_status_and_priority(status, priority)

    def get_tasks_with_due_date_range(self, start_date: date, end_date: date) -> List[Task]:
        return self.task_repo.get_tasks_with_due_date_range(start_date, end_date)

    def get_tasks_by_user_id(self, user_id: int) -> List[Task]:
        return self.task_repo.get_tasks_by_user_id(user_id)

    def get_task_count_by_status(self) -> Dict[str, int]:
        return self.task_repo.get_task_count_by_status()

    def get_overdue_tasks(self) -> List[Task]:
        return self.task_repo.get_overdue_tasks()

    def get_tasks_with_high_priority_and_due_soon(self) -> List[Task]:
        return self.task_repo.get_tasks_with_high_priority_and_due_soon()

    def get_tasks_with_status_and_created_range(self, status: str, start_created: datetime, end_created: datetime) -> List[Task]:
        return self.task_repo.get_tasks_with_status_and_created_range(status, start_created, end_created)

    def export_tasks_to_csv(self, file_path: str, filter_status: Optional[str] = None, filter_priority: Optional[int] = None) -> None:
        rows = self.task_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'title', 'description', 'status',
                'priority', 'due_date', 'created_at', 'updated_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.title, row.description, row.status,
                    row.priority, row.due_date, row.created_at, row.updated_at,
                ])

    def find_duplicate_tasks_by_title(self) -> List[Task]:
        tasks = self.task_repo.get_all()
        title_count = {}
        duplicates = []
        for task in tasks:
            title = task.title
            if title in title_count:
                title_count[title] += 1
                if title_count[title] == 2:
                    duplicates.append(task)
            else:
                title_count[title] = 1
        return duplicates

    def sum_task_priority_by_status(self) -> Dict[str, int]:
        results = {}
        for row in self.task_repo.list():
            key = row.status
            results[key] = results.get(key, 0) + row.priority
        return results

    def get_tasks_below_user_priority_threshold(self, user_id: int) -> List[Task]:
        tasks = self.task_repo.get_all()
        threshold = 3
        return [task for task in tasks if task.priority < threshold]

