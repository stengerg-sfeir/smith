"""BookRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import BookNotFoundError
from models import Book, Loan


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
            rows = conn.execute('SELECT COUNT(*) FROM books WHERE available = 1').fetchall()
            return rows[0][0] if rows else 0

    def get_books_borrowed_by_member(self, member_id: int) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT b.* FROM books b JOIN loans l ON b.id = l.book_id WHERE l.member_id = ?', (member_id,)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_overdue_loans_summary(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, COUNT(*) FROM loans WHERE due_date < return_date GROUP BY status').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_books_with_most_loans(self) -> list[tuple[Book, int]]:
        raise NotImplementedError()

    def get_loans_by_status(self, status: str) -> list[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM loans WHERE status = ?', (status,)).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def get_books_with_active_loans(self) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT DISTINCT b.* FROM books b JOIN loans l ON b.id = l.book_id WHERE l.status = "active"').fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_total_loans_by_member(self) -> dict[int, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT member_id, COUNT(*) FROM loans GROUP BY member_id').fetchall()
            return {row[0]: row[1] for row in rows}

