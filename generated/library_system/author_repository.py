"""AuthorRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Author, Book


class AuthorRepository:
    """SQLite repository for Author over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, author: Author) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO authors (name, birth_year, biography) VALUES (?, ?, ?)",
                (author.name, author.birth_year, author.biography),
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

    def list(self) -> List[Author]:
        return self.get_all()

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'birth_year', 'biography']
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

    def find_books_by_author(self, author_id: int) -> List[Book]:
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM books WHERE author_id = ?", (author_id,)
            ).fetchall()
            return [Book(**dict(row)) for row in cur.fetchall()]

    def get_author_books_count(self, author_id: int) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM books WHERE author_id = ?", (author_id,)
            ).fetchone()
            return cur[0] if cur else 0

    def get_author_with_most_books(self) -> Optional[Author]:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT a.id, a.name, a.birth_year, a.biography
                FROM authors a
                JOIN (
                    SELECT author_id, COUNT(*) as book_count
                    FROM books
                    GROUP BY author_id
                    ORDER BY book_count DESC
                    LIMIT 1
                ) b ON a.id = b.author_id
                """
            ).fetchone()
            if cur:
                return Author(**dict(cur))
            return None

    def get_books_by_author_and_year_range(self, author_id: int, start_year: int, end_year: int) -> List[Book]:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM books 
                WHERE author_id = ? AND year BETWEEN ? AND ?
                """,
                (author_id, start_year, end_year)
            ).fetchall()
            return [Book(**dict(row)) for row in cur]

    def get_books_by_author_and_copies_range(self, author_id: int, min_copies: int, max_copies: int) -> List[Book]:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM books 
                WHERE author_id = ? AND copies BETWEEN ? AND ?
                """,
                (author_id, min_copies, max_copies)
            ).fetchall()
            return [Book(**dict(row)) for row in cur]

