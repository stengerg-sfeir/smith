"""Service layer."""
from __future__ import annotations

import csv
import datetime
from sqlite3 import Connection
from typing import Any, Dict, List, Optional

from models import Task
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Connection) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)

    def get_tasks_by_status_and_priority(self, status: str, priority: int) -> List[Task]:
        return self.task_repo.get_tasks_by_status_and_priority(status, priority)

    def get_tasks_with_due_date_range(self, start_date: datetime.date, end_date: datetime.date) -> List[Task]:
        return self.task_repo.get_tasks_with_due_date_range(start_date, end_date)

    def get_tasks_by_user_id(self, user_id: int) -> List[Task]:
        return self.task_repo.get_tasks_by_user_id(user_id)

    def get_task_count_by_status(self) -> Dict[str, int]:
        return self.task_repo.get_task_count_by_status()

    def get_overdue_tasks(self) -> List[Task]:
        return self.task_repo.get_overdue_tasks()

    def get_tasks_with_high_priority_and_due_soon(self) -> List[Task]:
        return self.task_repo.get_tasks_with_high_priority_and_due_soon()

    def get_tasks_with_status_and_created_range(self, status: str, start_created: datetime.datetime, end_created: datetime.datetime) -> List[Task]:
        return self.task_repo.get_tasks_with_status_and_created_range(status, start_created, end_created)

    def export_tasks_to_csv(self, file_path: str, filter_status: Optional[str] = None, filter_priority: Optional[int] = None) -> None:
        rows = self.task_repo.list()
        filtered_rows = []
        if filter_status is not None:
            filtered_rows = [row for row in rows if row.status == filter_status]
        elif filter_priority is not None:
            filtered_rows = [row for row in rows if row.priority == filter_priority]
        else:
            filtered_rows = rows

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'title', 'description', 'status',
                'priority', 'due_date', 'created_at', 'updated_at',
            ])
            for row in filtered_rows:
                writer.writerow([
                    row.id, row.title, row.description, row.status,
                    row.priority, row.due_date, row.created_at, row.updated_at,
                ])

    def find_duplicate_tasks_by_title_and_status(self) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.task_repo.list():
            key = (row.title, row.status)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'title': key[0],
                    'status': key[1],
                    'count': len(group)
                })
        return results

    def get_tasks_below_priority_threshold(self, threshold: int) -> List[Task]:
        return self.task_repo.get_tasks_below_priority_threshold(threshold)
