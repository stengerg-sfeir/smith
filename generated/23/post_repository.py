"""PostRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Post


class PostRepository:
    """SQLite repository for Post over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, post: Post) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO posts (title, content, author_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (post.title, post.content, post.author_id, post.created_at, post.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Post]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM posts WHERE id = ?", (id,)
            ).fetchone()
            return Post(**dict(row)) if row else None

    def get_all(self) -> List[Post]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM posts ORDER BY id"
            ).fetchall()
            return [Post(**dict(r)) for r in rows]

    def list(self, author_id: Optional[Any] = None, content: Optional[Any] = None, title: Optional[Any] = None) -> List[Post]:
        with self.db.connect() as conn:
            query = "SELECT * FROM posts WHERE 1=1"
            params: List[Any] = []
            if author_id is not None:
                query += ' AND author_id = ?'
                params.append(author_id)
            if content is not None:
                query += ' AND content = ?'
                params.append(content)
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Post(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'content', 'author_id', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE posts SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM posts WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_posts_by_author(self, author_id: int) -> list[Post]:
        return self.list(
            author_id=author_id,
        )

    def get_posts_by_tag(self, tag_name: str) -> list[Post]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM posts r JOIN posttags j ON r.id = j.post_id JOIN tags o ON j.tag_id = o.id WHERE o.name = ?",
                (tag_name,)
            ).fetchall()
            return [Post(**dict(r)) for r in rows]

    def search_posts(self, title_contains: str, author_id: int, tag_name: str) -> list[Post]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM posts r JOIN authors o ON r.author_id = o.id WHERE o.id = ?",
                (author_id,)
            ).fetchall()
            return [Post(**dict(r)) for r in rows]

    def get_post_with_tags(self, post_id: int) -> Optional[Post]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchall()
            if not rows:
                return None
            row = rows[0]
            return Post(id=row[0], title=row[1], content=row[2], created_at=row[3], updated_at=row[4], author_id=row[5])

    def get_post_tag_counts(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT post_id AS k, COUNT(*) AS n FROM posttags GROUP BY post_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_posts_with_author_and_tag_info(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT p.id, p.title, p.content, p.created_at, p.updated_at, p.author_id,\n                a.name AS author_name, a.email AS author_email,\n                t.name AS tag_name\n                FROM posts p\n                JOIN authors a ON p.author_id = a.id\n                JOIN posttags pt ON p.id = pt.post_id\n                JOIN tags t ON pt.tag_id = t.id\n            ').fetchall()
            return [{'id': row[0], 'title': row[1], 'content': row[2], 'created_at': row[3], 'updated_at': row[4], 'author_id': row[5], 'author_name': row[6], 'author_email': row[7], 'tag_name': row[8]} for row in rows]

    def get_posts_with_tag_counts_and_author_info(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT \n                    p.id, \n                    p.title, \n                    p.content, \n                    p.created_at, \n                    p.updated_at, \n                    p.author_id,\n                    a.name AS author_name,\n                    a.email AS author_email,\n                    COUNT(t.id) AS tag_count\n                FROM posts p\n                JOIN authors a ON p.author_id = a.id\n                LEFT JOIN posttags pt ON p.id = pt.post_id\n                LEFT JOIN tags t ON pt.tag_id = t.id\n                GROUP BY p.id, p.title, p.content, p.created_at, p.updated_at, p.author_id, a.name, a.email\n            ').fetchall()
            return [{'id': row[0], 'title': row[1], 'content': row[2], 'created_at': row[3], 'updated_at': row[4], 'author_id': row[5], 'author_name': row[6], 'author_email': row[7], 'tag_count': row[8]} for row in rows]


    def search_posts_by_tag(self, *args, **kwargs):
        return self.search_posts(*args, **kwargs)


    def get_posts_with_tag_counts(self, *args, **kwargs):
        return self.get_posts_with_tag_counts_and_author_info(*args, **kwargs)


