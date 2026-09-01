"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from database import Database
from models import Project
from project_repository import ProjectRepository
from task_repository import TaskRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.task_repo = TaskRepository(db)

    def list_project(self, title: Optional[str] = None, description: Optional[str] = None, created_at: Optional[str] = None, created_at_end: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = self.project_repo.list(title=title, description=description, created_at=created_at, created_at_end=created_at_end)
        total = sum(e.title for e in rows)
        return {'projects': total}

    def add_project(self, title: str, description: Optional[str] = None) -> bool:
        project = Project(title=title, description=description, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.project_repo.create(project)

    def delete_project(self, id: int) -> bool:
        return self.project_repo.delete(id)

    def update_task(self, id: int, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None, priority: Optional[int] = None, project_id: Optional[int] = None) -> bool:
        data = {k: v for k, v in {'title': title, 'description': description, 'status': status, 'priority': priority, 'project_id': project_id}.items() if v is not None}
        return self.task_repo.update(id, data)

