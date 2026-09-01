"""BookRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import BookNotFoundError
from models import Book


class BookRepository:
    """SQLite repository for Book over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, book: Book) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO books (title, author, isbn, available) VALUES (?, ?, ?, ?)",
                (book.title, book.author, book.isbn, book.available),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Book]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM books WHERE id = ?", (id,)
            ).fetchone()
            return Book(**dict(row)) if row else None

    def get_all(self) -> List[Book]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM books ORDER BY id"
            ).fetchall()
            return [Book(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, author: Optional[Any] = None, isbn: Optional[Any] = None, available: Optional[Any] = None) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if author is not None:
                query += ' AND author = ?'
                params.append(author)
            if isbn is not None:
                query += ' AND isbn = ?'
                params.append(isbn)
            if available is not None:
                query += ' AND available = ?'
                params.append(available)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Book(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'author', 'isbn', 'available']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE books SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise BookNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM books WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

