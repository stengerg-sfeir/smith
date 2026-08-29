"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from document_repository import DocumentRepository
from exceptions import (
    AuthenticationError,
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
            raise AuthenticationError('Invalid email or password')
        if not user.password_hash or not self._verify_password(password, user.password_hash):
            raise AuthenticationError('Invalid email or password')
        return user

    def validate_user_permissions(self, user_id: int, action: str, document_id: int) -> bool:
        if not self.check_document_access(user_id, document_id):
            raise PermissionError('User does not have access to this document')
        permissions = self.user_repo.get_user_document_permissions(user_id)
        action_map = {'read': 'read', 'edit': 'edit', 'delete': 'delete'}
        if action not in action_map:
            raise PermissionError(f'Invalid action: {action}')
        return permissions.get(action_map[action], False)

    def get_user_documents(self, user_id: int, title_filter: Optional[str]=None, created_after: Optional[datetime.datetime]=None, created_before: Optional[datetime.datetime]=None) -> List[Document]:
        return self.document_repo.get_documents_by_user_and_filter(user_id=user_id, title_filter=title_filter, created_after=created_after, created_before=created_before, status_filter=None)

    def search_documents_by_user(self, user_id: int, query: str) -> List[Document]:
        return self.document_repo.search_documents_by_content_and_user(query=query, user_id=user_id)

    def check_document_access(self, user_id: int, document_id: int) -> bool:
        document = self.document_repo.get_document_by_id_and_user(document_id, user_id)
        if not document:
            return False
        permissions = self.user_repo.get_user_document_permissions(user_id)
        return permissions.get('read', False)

