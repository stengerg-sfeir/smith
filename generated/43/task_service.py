"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from database import Database
from exceptions import (
    NotFoundError,
)
from models import Project
from priority_repository import PriorityRepository
from project_repository import ProjectRepository
from status_repository import StatusRepository
from task_repository import TaskRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.priority_repo = PriorityRepository(db)
        self.project_repo = ProjectRepository(db)
        self.status_repo = StatusRepository(db)
        self.task_repo = TaskRepository(db)

    def add_project(self, name: str, description: Optional[str] = None) -> None:
        project = Project(name=name, description=description, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.project_repo.create(project)

    def set_priority(self, project_id: int, priority_id: int) -> None:
        """Set a priority for a project by updating the project's priority field."""
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundError(f'Project with id {project_id} not found')
        priority = self.priority_repo.get_by_id(priority_id)
        if not priority:
            raise NotFoundError(f'Priority with id {priority_id} not found')
        project_data = {'priority': priority.id}
        self.project_repo.update(project_id, project_data)

    def update_status(self, id: int, name: str) -> None:
        data = {k: v for k, v in {'name': name}.items() if v is not None}
        return self.status_repo.update(id, data)

    def list_project(self, name: Optional[str] = None, description: Optional[str] = None, created_at: Optional[str] = None, created_at_end: Optional[str] = None, updated_at: Optional[str] = None, updated_at_end: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.project_repo.list(name=name, description=description, created_at=created_at, created_at_end=created_at_end, updated_at=updated_at, updated_at_end=updated_at_end)

