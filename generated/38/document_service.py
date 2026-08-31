"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from database import Database
from document_repository import DocumentRepository
from models import Document
from user_repository import UserRepository


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.user_repo = UserRepository(db)

    def authenticate_user(self, user_id: int) -> bool:
        """Authenticate a user by user_id. Returns True if user exists and is valid, False otherwise."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return False
        return True

    def list_document(self, title: Optional[str] = None, created_at: Optional[str] = None, created_at_end: Optional[str] = None) -> List[Dict[str, Any]]:
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

