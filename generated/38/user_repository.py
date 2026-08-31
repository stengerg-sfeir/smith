"""UserRepository data access."""
from __future__ import annotations

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

    def list(self, created_at: Optional[Any] = None, email: Optional[Any] = None) -> List[User]:
        with self.db.connect() as conn:
            query = "SELECT * FROM users WHERE 1=1"
            params: List[Any] = []
            if created_at is not None:
                query += ' AND created_at = ?'
                params.append(created_at)
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
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Document(**dict(r)) for r in rows]

    def get_document_count_by_user(self, user_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM documents WHERE user_id = ?', (user_id,)).fetchone()
            return row[0] if row else 0

    def get_user_document_access_summary(self, user_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute("\n                SELECT \n                    COUNT(*) as total_documents,\n                    COUNT(CASE WHEN updated_at >= datetime('now', '-30 days') THEN 1 END) as updated_in_last_30_days,\n                    COUNT(CASE WHEN created_at >= datetime('now', '-30 days') THEN 1 END) as created_in_last_30_days\n                FROM documents \n                WHERE user_id = ?\n            ", (user_id,)).fetchall()
            result = rows[0] if rows else None
            return {'total_documents': result[0] if result else 0, 'updated_in_last_30_days': result[1] if result else 0, 'created_in_last_30_days': result[2] if result else 0}

    def search_documents_by_title(self, query: str, user_id: int) -> list[Document]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM documents WHERE user_id = ? AND title LIKE ?', (user_id, f'%{query}%')).fetchall()
            return [Document(**dict(r)) for r in rows]

    def get_user_with_documents(self, user_id: int) -> dict[str, any]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT u.*, d.id as document_id, d.title, d.content, d.created_at, d.updated_at FROM users u LEFT JOIN documents d ON u.id = d.user_id WHERE u.id = ?', (user_id,)).fetchall()
            user_data = rows[0] if rows else None
            if not user_data:
                return {}
            user_dict = {'id': user_data[0], 'email': user_data[1], 'created_at': user_data[2], 'updated_at': user_data[3], 'documents': []}
            for row in rows:
                if row[4] is not None:
                    user_dict['documents'].append({'id': row[4], 'title': row[5], 'content': row[6], 'created_at': row[7], 'updated_at': row[8]})
            return user_dict

