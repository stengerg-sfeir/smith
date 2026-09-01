"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from database import Database
from document_repository import DocumentRepository
from exceptions import (
    DocumentNotFoundError,
    PermissionDeniedError,
)
from models import Document


class DocumentService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.document_repo = DocumentRepository(db)

    def add(self, title: str, content: str, file_path: str, author_id: int) -> bool:
        try:
            document = Document(author_id=author_id, content=content, created_at=datetime.datetime.utcnow(), file_path=file_path, title=title, version=1, updated_at=datetime.datetime.utcnow())
            self.document_repo.create(document)
            return True
        except Exception as e:
            raise e

    def list(self, author_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, keywords: Optional[str] = None) -> List[Dict]:
        results = {}
        for row in self.document_repo.list(author_id=author_id):
            key = row.author_id
            results[key] = results.get(key, 0) + row.version
        return results

    def update(self, title: str, content: str, file_path: str) -> bool:
        try:
            raise PermissionDeniedError('Author ID is required to update a document.')
        except Exception as e:
            raise e

    def delete(self, title: str, author_id: int) -> bool:
        try:
            document = self.document_repo.get_document_by_title_and_author(title, author_id)
            if not document:
                raise DocumentNotFoundError(f"Document with title '{title}' and author ID {author_id} not found.")
            self.document_repo.delete(document.id)
            return True
        except Exception as e:
            raise e

