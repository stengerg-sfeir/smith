"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from document_repository import DocumentRepository
from models import Document, User
from user_repository import UserRepository


class DocumentService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.user_repo = UserRepository(db)

    def authenticate_user(self, id: int) -> bool:
        user = self.user_repo.get_by_id(id)
        return user is not None

    def list_document(self, title: Optional[str] = None, created_at: Optional[str] = None, created_at_end: Optional[str] = None) -> list[dict]:
        results = {}
        for row in self.document_repo.list(title=title, created_at=created_at, created_at_end=created_at_end):
            key = (row.title, row.created_at)
            results[key] = results.get(key, 0) + row.id
        return results

    def add_document(self, title: str, content: str, user_id: int) -> bool:
        document = Document(title=title, content=content, user_id=user_id, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.document_repo.create(document)

    def update_document(self, id: int, title: Optional[str] = None, content: Optional[str] = None, user_id: int = None) -> bool:
        data = {k: v for k, v in {'title': title, 'content': content, 'user_id': user_id}.items() if v is not None}
        return self.document_repo.update(id, data)

    def delete_document(self, id: int) -> bool:
        return self.document_repo.delete(id)

    def add_user(self, email: str, password_hash: str) -> bool:
        user = User(email=email, password_hash=password_hash, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.user_repo.create(user)

