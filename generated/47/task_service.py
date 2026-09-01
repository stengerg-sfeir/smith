"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from exceptions import (
    NotFoundError,
)
from models import Project, Task
from person_repository import PersonRepository
from project_repository import ProjectRepository
from task_repository import TaskRepository


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.person_repo = PersonRepository(db)
        self.project_repo = ProjectRepository(db)
        self.task_repo = TaskRepository(db)

    def add_project(self, name: str, description: Optional[str] = None) -> None:
        project = Project(name=name, description=description, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.project_repo.create(project)

    def assign_person(self, task_id: int, person_id: int) -> None:
        """
            Assign a person to a task by updating the task's assigned_to field.
        
            Args:
                task_id: The ID of the task to assign
                person_id: The ID of the person to assign to the task
            
            Raises:
                NotFoundError: If the task or person does not exist
                ValidationError: If the person is not valid or task is invalid
            """
        task = self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(f'Task with id {task_id} not found')
        person = self.person_repo.get_by_id(person_id)
        if not person:
            raise NotFoundError(f'Person with id {person_id} not found')
        task_data = {'assigned_to': person_id}
        self.task_repo.update(task_id, task_data)

    def list_project(self) -> List[Project]:
        return self.project_repo.list()

    def list_task(self, project_id: Optional[str] = None, status: Optional[str] = None) -> List[Task]:
        return self.task_repo.list(project_id=project_id, status=status)

