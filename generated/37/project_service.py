"""Service layer."""
from __future__ import annotations

from database import Database
from project_repository import ProjectRepository
from task_repository import TaskRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.task_repo = TaskRepository(db)

    def delete_project(self, id: int) -> bool:
        return self.project_repo.delete(id)

