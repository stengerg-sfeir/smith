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
                "INSERT INTO books (title, author, isbn, available_copies, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (book.title, book.author, book.isbn, book.available_copies, book.created_at, book.updated_at),
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

    def list(self, title: Optional[Any] = None, author: Optional[Any] = None, isbn: Optional[Any] = None, available_copies: Optional[Any] = None) -> List[Book]:
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
            if available_copies is not None:
                query += ' AND available_copies = ?'
                params.append(available_copies)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Book(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'author', 'isbn', 'available_copies', 'created_at', 'updated_at']
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

    def get_books_by_author(self, author: str) -> list[Book]:
        return self.list(
            author=author,
        )

    def get_books_by_isbn_range(self, min_isbn: str, max_isbn: str) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM books WHERE isbn BETWEEN ? AND ?', (min_isbn, max_isbn)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_available_books_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM books",
            ).fetchone()
            return int(row["n"])

    def get_books_with_loans_count(self) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT b.id, b.title, b.author, b.isbn, b.available_copies, b.created_at, b.updated_at\n                FROM books b\n                LEFT JOIN loans l ON b.id = l.book_id\n                GROUP BY b.id\n                ORDER BY COUNT(l.id) DESC\n                ').fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_due_within_next_week(self) -> list[Book]:
        with self.db.connect() as conn:
            today = conn.execute("SELECT datetime('now')").fetchone()[0]
            next_week = conn.execute("SELECT datetime('now', '+7 days')").fetchone()[0]
            rows = conn.execute('\n                SELECT b.id, b.title, b.author, b.isbn, b.available_copies, b.created_at, b.updated_at\n                FROM books b\n                JOIN loans l ON b.id = l.book_id\n                WHERE l.due_date BETWEEN ? AND ?\n                ', (today, next_week)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_borrowed_by_member(self, member_id: int) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM books r JOIN loans j ON r.id = j.book_id JOIN members o ON j.member_id = o.id WHERE o.name = ?",
                (member_id,)
            ).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_with_low_availability(self) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM books WHERE available_copies <= 1').fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_by_title_contains(self, title: str) -> list[Book]:
        return self.list(
            title=title,
        )

