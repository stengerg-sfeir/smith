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
            rows = conn.execute('SELECT * FROM books WHERE author_id = ?', (author_id,)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_author_books_count(self, author_id: int) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) AS count FROM books WHERE author_id = ?', (author_id,)).fetchone()
            return rows['count'] if rows else 0

    def get_author_with_most_books(self) -> Optional[Author]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM authors ORDER BY (SELECT COUNT(*) FROM books WHERE books.author_id = authors.id) DESC LIMIT 1').fetchall()
            if not rows:
                return None
            return Author(**dict(rows[0]))

    def get_books_by_author_and_year_range(self, author_id: int, start_year: int, end_year: int) -> List[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM books WHERE author_id = ? AND published_year BETWEEN ? AND ?', (author_id, f'{start_year}-01-01', f'{end_year}-12-31')).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_by_author_and_copies_range(self, author_id: int, min_copies: int, max_copies: int) -> List[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM books WHERE author_id = ? AND available_copies BETWEEN ? AND ?', (author_id, min_copies, max_copies)).fetchall()
            return [Book(**dict(r)) for r in rows]

