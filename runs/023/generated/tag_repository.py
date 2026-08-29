"""TagRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Tag


class TagRepository:
    """SQLite repository for Tag over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, tag: Tag) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tags (name, created_at, updated_at) VALUES (?, ?, ?)",
                (tag.name, tag.created_at, tag.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Tag]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tags WHERE id = ?", (id,)
            ).fetchone()
            return Tag(**dict(row)) if row else None

    def get_all(self) -> List[Tag]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tags ORDER BY id"
            ).fetchall()
            return [Tag(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None) -> List[Tag]:
        with self.db.connect() as conn:
            query = "SELECT * FROM tags WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Tag(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tags SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM tags WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_tags_by_post_id(self, post_id: int) -> list[Tag]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM tags r JOIN posttags j ON r.id = j.tag_id JOIN posts o ON j.post_id = o.id WHERE o.name = ?",
                (post_id,)
            ).fetchall()
            return [Tag(**dict(r)) for r in rows]

    def get_posts_with_tag_counts(self) -> list[dict[str, any]]:
        query = '\n            SELECT \n                p.id, \n                p.title, \n                p.content, \n                p.created_at, \n                p.updated_at, \n                p.author_id,\n                COUNT(pt.tag_id) AS tag_count\n            FROM posts p\n            LEFT JOIN posttags pt ON p.id = pt.post_id\n            LEFT JOIN tags t ON pt.tag_id = t.id\n            GROUP BY p.id, p.title, p.content, p.created_at, p.updated_at, p.author_id\n        '
        with self.db.connect() as conn:
            conn.execute('PRAGMA foreign_keys = OFF')
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def get_tag_usage_stats(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT tag_id AS k, COUNT(*) AS n FROM posttags GROUP BY tag_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def search_tags_by_name(self, name_contains: str) -> list[Tag]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tags WHERE name LIKE ?",
                ("%" + name_contains + "%",)
            ).fetchall()
            return [Tag(**dict(r)) for r in rows]

    def get_tag_by_name(self, name: str) -> Optional[Tag]:
        query = 'SELECT * FROM tags WHERE name = ?'
        with self.db.connect() as conn:
            row = conn.execute(query, (name,)).fetchone()
            if row is None:
                return None
            return Tag(**dict(row))

    def get_tag_count_by_name(self, name: str) -> int:
        query = 'SELECT COUNT(*) FROM tags WHERE name = ?'
        with self.db.connect() as conn:
            result = conn.execute(query, (name,)).fetchone()
            return result[0] if result else 0

