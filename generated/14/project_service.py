"""Service layer."""
from __future__ import annotations

import datetime

from database import Database
from models import Project
from project_repository import ProjectRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)

    def add_project(self, name: str, description: str, status: str) -> bool:
        project = Project(name=name, description=description, status=status, created_at=datetime.datetime.now().isoformat(), deleted_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.project_repo.create(project)

    def update_project(self, id: int, name: str, description: str, status: str) -> bool:
        data = {k: v for k, v in {'name': name, 'description': description, 'status': status}.items() if v is not None}
        return self.project_repo.update(id, data)

    def list_project(self, name: str, status: str, created_at: str, created_at_end: str) -> list[Project]:
        return self.project_repo.list(name=name, status=status, created_at=created_at, created_at_end=created_at_end)

    def delete_project(self, id: int) -> bool:
        return self.project_repo.delete(id)

