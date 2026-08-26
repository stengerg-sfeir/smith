"""UserRepository data access."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from database import Database
from models import Document, User


class UserRepository:
    """SQLite repository for User over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, user: User) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (user.email, user.password_hash, user.created_at, user.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[User]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (id,)
            ).fetchone()
            return User(**dict(row)) if row else None

    def get_all(self) -> List[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY id"
            ).fetchall()
            return [User(**dict(r)) for r in rows]

    def list(self, email: Optional[Any] = None) -> List[User]:
        with self.db.connect() as conn:
            query = "SELECT * FROM users WHERE 1=1"
            params: List[Any] = []
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [User(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['email', 'password_hash', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM users WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.list(
            email=email,
        )

    def get_documents_by_user_id(self, user_id: int, title_filter: Optional[str]=None, created_after: Optional[str]=None, created_before: Optional[str]=None) -> list[Document]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM documents WHERE user_id = ?'
            params = [user_id]
            if title_filter:
                query += ' AND title LIKE ?'
                params.append(f'%{title_filter}%')
            if created_after:
                query += ' AND created_at >= ?'
                params.append(created_after)
            if created_before:
                query += ' AND created_at <= ?'
                params.append(created_before)
            query += ' ORDER BY created_at DESC'
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [Document(**dict(r)) for r in rows]

    def get_document_count_by_user(self, user_id: int) -> int:
        with self.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT COUNT(*) AS count FROM documents WHERE user_id = ?', [user_id]).fetchone()
            return row['count'] if row else 0

    def search_documents_by_title(self, query: str, user_id: int) -> list[Document]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM documents WHERE user_id = ? AND title LIKE ? ORDER BY created_at DESC'
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, [user_id, f'%{query}%']).fetchall()
            return [Document(**dict(r)) for r in rows]

    def get_user_document_permissions(self, user_id: int) -> dict[str, bool]:
        return {}

