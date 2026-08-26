"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from document_repository import DocumentRepository
from exceptions import (
    NotFoundError,
    PermissionError,
)
from models import Document, User
from user_repository import UserRepository


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.user_repo = UserRepository(db)

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        user = self.user_repo.get_user_by_email(email)
        if not user:
            raise NotFoundError(f'User with email {email} not found')
        return user

    def validate_user_permissions(self, user_id: int, action: str, document_id: int) -> bool:
        raise NotImplementedError()

    def get_user_documents(self, user_id: int, title_filter: Optional[str]=None, created_after: Optional[datetime.datetime]=None, created_before: Optional[datetime.datetime]=None) -> List[Document]:
        """
            Retrieve documents for a given user with optional filtering by title, creation date range, and other criteria.
        
            Args:
                user_id: ID of the user whose documents to retrieve
                title_filter: Optional filter for document titles
                created_after: Optional filter for documents created after this datetime
                created_before: Optional filter for documents created before this datetime
            
            Returns:
                List of Document objects matching the criteria
            """
        return self.document_repo.get_documents_by_user_and_filter(user_id=user_id, title_filter=title_filter, created_after=created_after, created_before=created_before, status_filter=None)

    def search_documents_by_user(self, user_id: int, query: str) -> List[Document]:
        """
            Search for documents by user ID and query content or title.
        
            Args:
                user_id: ID of the user to search documents for
                query: Search query string (can match title or content)
        
            Returns:
                List of matching documents
            """
        title_results = self.user_repo.search_documents_by_title(query, user_id)
        content_results = self.document_repo.search_documents_by_content_and_user(query, user_id)
        all_results = set()
        results = []
        for doc in title_results:
            if doc.id not in all_results:
                all_results.add(doc.id)
                results.append(doc)
        for doc in content_results:
            if doc.id not in all_results:
                all_results.add(doc.id)
                results.append(doc)
        return results

    def check_document_access(self, user_id: int, document_id: int) -> bool:
        document = self.document_repo.get_by_id(document_id)
        if not document:
            raise NotFoundError(f'Document with id {document_id} not found')
        if document.user_id != user_id:
            user_permissions = self.user_repo.get_user_document_permissions(user_id)
            if document_id not in user_permissions or not user_permissions.get(str(document_id), False):
                raise PermissionError(f'User {user_id} does not have permission to access document {document_id}')
        return True

