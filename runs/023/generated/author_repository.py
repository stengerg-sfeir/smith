"""AuthorRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Author, Post


class AuthorRepository:
    """SQLite repository for Author over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, author: Author) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO authors (name, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (author.name, author.email, author.created_at, author.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Author]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM authors WHERE id = ?", (id,)
            ).fetchone()
            return Author(**dict(row)) if row else None

    def get_all(self) -> List[Author]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM authors ORDER BY id"
            ).fetchall()
            return [Author(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None) -> List[Author]:
        with self.db.connect() as conn:
            query = "SELECT * FROM authors WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Author(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE authors SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM authors WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_posts_by_tag(self, tag_name: str) -> list[Post]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT p.* FROM posts p JOIN posttags pt ON p.id = pt.post_id JOIN tags t ON pt.tag_id = t.id WHERE t.name = ?', (tag_name,))
            rows = cursor.fetchall()
            return [Post(**dict(r)) for r in rows]

    def get_posts_with_tag_counts(self, tag_name: str) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT p.id, p.title, p.content, p.created_at, p.updated_at, p.author_id FROM posts p JOIN posttags pt ON p.id = pt.post_id JOIN tags t ON pt.tag_id = t.id WHERE t.name = ?', (tag_name,))
            rows = cursor.fetchall()
            post_list = [Post(**dict(r)) for r in rows]
            count = len(post_list)
            return {tag_name: count}

    def search_posts_by_tag(self, tag_name: str, title_contains: str) -> list[Post]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT p.* FROM posts p JOIN posttags pt ON p.id = pt.post_id JOIN tags t ON pt.tag_id = t.id WHERE t.name = ? AND p.title LIKE ?', (tag_name, f'%{title_contains}%'))
            rows = cursor.fetchall()
            return [Post(**dict(r)) for r in rows]

    def get_tag_usage_stats(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT t.name, COUNT(pt.post_id) AS post_count FROM tags t LEFT JOIN posttags pt ON t.id = pt.tag_id GROUP BY t.name')
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    def get_author_posts_count(self, author_id: int) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(p.id) FROM posts p WHERE p.author_id = ?', (author_id,))
            result = cursor.fetchone()
            return result[0] if result else 0

