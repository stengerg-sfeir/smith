"""DocumentRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import DocumentNotFoundError
from models import Document


class DocumentRepository:
    """SQLite repository for Document over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, document: Document) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO documents (title, content, file_path, created_at, updated_at, author_id, version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (document.title, document.content, document.file_path, document.created_at, document.updated_at, document.author_id, document.version),
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

    def list(self, title: Optional[Any] = None, author_id: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, content: Optional[Any] = None, file_path: Optional[Any] = None) -> List[Document]:
        with self.db.connect() as conn:
            query = "SELECT * FROM documents WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if author_id is not None:
                query += ' AND author_id = ?'
                params.append(author_id)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            if content is not None:
                query += ' AND content = ?'
                params.append(content)
            if file_path is not None:
                query += ' AND file_path = ?'
                params.append(file_path)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Document(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'content', 'file_path', 'created_at', 'updated_at', 'author_id', 'version']
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
                raise DocumentNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM documents WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_document_by_title_and_author(self, title: str, author_id: int) -> Optional[Document]:
        return self.list(
            title=title,
            author_id=author_id,
        )

    def list_documents_by_author_and_date_range(self, author_id: int, start_date: datetime, end_date: datetime) -> List[Document]:
        return []

    def count_documents_by_author(self, author_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(version), 0) AS v FROM documents WHERE author_id = ?",
                (author_id,)
            ).fetchone()
            return int(row["v"])

    def get_document_versions_for_author(self, author_id: int) -> Dict[int, List[Document]]:
        return self.list(
            author_id=author_id,
        )

    def search_documents_by_keywords(self, keywords: str) -> List[Document]:
        return []

    def get_document_with_latest_version(self, title: str) -> Optional[Document]:
        return self.list(
            title=title,
        )

    def list_documents_with_content_summary(self, max_chars: int) -> List[Document]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT id, title, content, file_path, author_id, created_at, updated_at, version FROM documents ORDER BY created_at DESC').fetchall()
        return [Document(id=row[0], title=row[1], content=row[2][:max_chars] if len(row[2]) > max_chars else row[2], file_path=row[3], author_id=row[4], created_at=row[5], updated_at=row[6], version=row[7]) for row in rows]

