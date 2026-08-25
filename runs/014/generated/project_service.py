"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Optional

from database import Database
from models import Project
from project_repository import ProjectRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)

    def create_project(self, name: str, description: Optional[str] = None, status: str = None) -> Project:
        project = Project(name=name, description=description, status=status, created_at=datetime.datetime.now().isoformat(), deleted_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.project_repo.create(project)

    def update_project(self, project_id: int, name: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None) -> Optional[Project]:
        data = {k: v for k, v in {'name': name, 'description': description, 'status': status}.items() if v is not None}
        return self.project_repo.update(project_id, data)

    def list_projects(self, status: Optional[str] = None, query: Optional[str] = None) -> list[Project]:
        return self.project_repo.list(status=status)

    def list_active_projects(self) -> list[Project]:
        """Retrieve all active projects from the repository."""
        return self.project_repo.list_active_projects()

    def delete_project(self, project_id: int) -> bool:
        return self.project_repo.delete(project_id)

    def export_projects_to_csv(self, file_path: str, status_filter: Optional[str] = None) -> None:
        rows = self.project_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'description', 'status',
                'created_at', 'updated_at', 'deleted_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.name, row.description, row.status,
                    row.created_at, row.updated_at, row.deleted_at,
                ])

    def get_project_stats(self) -> dict:
        return self.project_repo.get_project_stats()

