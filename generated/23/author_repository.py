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

    def list(self, email: Optional[Any] = None, name: Optional[Any] = None) -> List[Author]:
        with self.db.connect() as conn:
            query = "SELECT * FROM authors WHERE 1=1"
            params: List[Any] = []
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
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
            rows = conn.execute('SELECT * FROM posts JOIN posttags ON posts.id = posttags.post_id JOIN tags ON posttags.tag_id = tags.id WHERE tags.name = ?', (tag_name,)).fetchall()
            return [Post(**dict(r)) for r in rows]

    def get_posts_with_tag_counts(self, tag_name: str) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT posts.id, posts.title, posts.content, posts.created_at, posts.updated_at, posts.author_id, tags.name AS tag_name FROM posts JOIN posttags ON posts.id = posttags.post_id JOIN tags ON posttags.tag_id = tags.id WHERE tags.name = ?', (tag_name,)).fetchall()
            return {row['title']: 1 for row in rows}

    def search_posts_by_tag(self, tag_name: str, title_contains: str) -> list[Post]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM posts JOIN posttags ON posts.id = posttags.post_id JOIN tags ON posttags.tag_id = tags.id WHERE tags.name = ? AND posts.title LIKE ?', (tag_name, f'%{title_contains}%')).fetchall()
            return [Post(**dict(r)) for r in rows]

    def get_tag_usage_stats(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT author_id AS k, COUNT(*) AS n FROM posts GROUP BY author_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_author_posts_count(self, author_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM posts WHERE author_id = ?', (author_id,)).fetchone()
            return row[0] if row else 0

