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
            cursor = conn.cursor()
            cursor.execute('SELECT t.* FROM tags t JOIN posttags pt ON t.id = pt.tag_id WHERE pt.post_id = ?', (post_id,))
            rows = cursor.fetchall()
            return [Tag(**dict(r)) for r in rows]

    def get_posts_with_tag_counts(self) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT p.*, COUNT(t.id) AS tag_count \n                FROM posts p \n                LEFT JOIN posttags pt ON p.id = pt.post_id \n                LEFT JOIN tags t ON pt.tag_id = t.id \n                GROUP BY p.id\n            ')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_tag_usage_stats(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT t.name, COUNT(pt.tag_id) AS usage_count \n                FROM tags t \n                LEFT JOIN posttags pt ON t.id = pt.tag_id \n                GROUP BY t.name\n            ')
            rows = cursor.fetchall()
            result: dict[str, int] = {}
            for row in rows:
                result[row[0]] = row[1]
            return result

    def search_tags_by_name(self, name_contains: str) -> list[Tag]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tags WHERE name LIKE ?', (f'%{name_contains}%',))
            rows = cursor.fetchall()
            return [Tag(**dict(r)) for r in rows]

    def get_tag_by_name(self, name: str) -> Optional[Tag]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tags WHERE name = ?', (name,))
            row = cursor.fetchone()
            return Tag(**dict(row)) if row else None

    def get_tag_count_by_name(self, name: str) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM tags WHERE name = ?', (name,))
            result = cursor.fetchone()
            return result[0] if result else 0

