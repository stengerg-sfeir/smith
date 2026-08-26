"""DocumentRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Document


class DocumentRepository:
    """SQLite repository for Document over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, document: Document) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO documents (title, content, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (document.title, document.content, document.user_id, document.created_at, document.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Document]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?", (id,)
            ).fetchone()
            return Document(**dict(row)) if row else None

    def get_all(self) -> List[Document]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY id"
            ).fetchall()
            return [Document(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, user_id: Optional[Any] = None) -> List[Document]:
        with self.db.connect() as conn:
            query = "SELECT * FROM documents WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Document(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'content', 'user_id', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE documents SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM documents WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_documents_by_user_and_filter(self, user_id: int, title_filter: Optional[str] = None, created_after: Optional[datetime] = None, created_before: Optional[datetime] = None, status_filter: Optional[str] = None) -> list[Document]:
        return self.list(
            user_id=user_id,
        )

    def get_document_by_id_and_user(self, document_id: int, user_id: int) -> Optional[Document]:
        return self.list(
            user_id=user_id,
        )

    def search_documents_by_content_and_user(self, query: str, user_id: int) -> list[Document]:
        return self.list(
            user_id=user_id,
        )

    def get_document_count_by_user_and_filter(self, user_id: int, title_filter: Optional[str] = None, created_after: Optional[datetime] = None, created_before: Optional[datetime] = None) -> int:
        return self.list(
            user_id=user_id,
        )

    def get_recent_documents_by_user(self, user_id: int, limit: int) -> list[Document]:
        return self.list(
            user_id=user_id,
        )

    def get_documents_with_user_metadata(self, user_id: int, include_permissions: bool) -> list[Document]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT d.*, u.email, u.id AS user_id \n                   FROM documents d \n                   JOIN users u ON d.user_id = u.id \n                   WHERE d.user_id = ?', (user_id,))
            rows = cursor.fetchall()
            return [Document(**dict(r)) for r in rows]

