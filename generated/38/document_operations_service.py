"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import List, Optional

from database import Database
from document_repository import DocumentRepository
from models import Document
from user_repository import UserRepository


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.user_repo = UserRepository(db)

    def get_user_documents(self, user_id: int, title_filter: Optional[str]=None, created_after: Optional[datetime.datetime]=None, created_before: Optional[datetime.datetime]=None) -> List[Document]:
        """
            Retrieve documents for a given user with optional filtering by title, creation date range.
            """
        return self.document_repo.get_documents_by_user_and_filter(user_id=user_id, title_filter=title_filter, created_after=created_after, created_before=created_before, status_filter=None)

    def search_documents_by_user(self, user_id: int, query: str) -> List[Document]:
        """
            Search documents by content for a given user.
            """
        return self.document_repo.search_documents_by_content_and_user(query=query, user_id=user_id)

    def export_user_documents_to_csv(self, user_id: int, title_filter: Optional[str] = None, created_after: Optional[datetime] = None, created_before: Optional[datetime] = None, file_path: str = None) -> None:
        rows = self.document_repo.list(user_id=user_id, )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'title', 'content', 'user_id',
                'created_at', 'updated_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.title, row.content, row.user_id,
                    row.created_at, row.updated_at,
                ])

    def find_duplicate_document_titles(self, user_id: int) -> List[Document]:
        """
            Find documents with duplicate titles for a given user.
            """
        documents = self.get_user_documents(user_id=user_id)
        title_to_docs = {}
        for doc in documents:
            title = doc.title
            if title not in title_to_docs:
                title_to_docs[title] = []
            title_to_docs[title].append(doc)
        duplicates = []
        for title, docs in title_to_docs.items():
            if len(docs) > 1:
                duplicates.extend(docs)
        return duplicates

    def get_recent_documents(self, user_id: int, limit: int) -> List[Document]:
        """
            Retrieve the most recently created documents for a user, limited by count.
            """
        return self.document_repo.get_recent_documents_by_user(user_id=user_id, limit=limit)

    def check_document_access(self, user_id: int, document_id: int) -> bool:
        """
            Check if a user has access to a document based on permissions.
            """
        document = self.document_repo.get_document_by_id_and_user(document_id=document_id, user_id=user_id)
        if not document:
            return False
        user_permissions = self.user_repo.get_user_document_permissions(user_id=user_id)
        if not user_permissions:
            return False
        return document_id in user_permissions and user_permissions[str(document_id)]

