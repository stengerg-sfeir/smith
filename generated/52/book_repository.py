"""BookRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import BookNotFoundError
from models import Book, BorrowRecord


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

    def list(self, title: Optional[Any] = None, author: Optional[Any] = None, available: Optional[Any] = None, max_isbn: Optional[Any] = None, min_isbn: Optional[Any] = None) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if author is not None:
                query += ' AND author = ?'
                params.append(author)
            if available is not None:
                query += ' AND available = ?'
                params.append(available)
            if max_isbn is not None:
                query += ' AND id <= ?'
                params.append(max_isbn)
            if min_isbn is not None:
                query += ' AND id >= ?'
                params.append(min_isbn)
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
        return self.list(
            min_isbn=min_isbn,
            max_isbn=max_isbn,
        )

    def get_available_books(self) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM books WHERE available = 1').fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_borrowed_by_member(self, member_id: int) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM books r JOIN borrow_records j ON r.id = j.book_id JOIN members o ON j.member_id = o.id WHERE o.name = ?",
                (member_id,)
            ).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_total_books_borrowed_by_member(self, member_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) AS count FROM borrow_records WHERE member_id = ?', (member_id,)).fetchone()
            return row[0] if row else 0

    def get_total_books_available(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT SUM(available) AS total FROM books').fetchone()
            return row[0] if row else 0

    def get_books_borrowed_in_date_range(self, start_date: datetime, end_date: datetime) -> list[Book]:
        return []

    def get_overdue_borrow_records(self) -> list[BorrowRecord]:
        with self.db.connect() as conn:
            rows = conn.execute("\n                SELECT * FROM borrow_records \n                WHERE return_date IS NULL \n                AND borrow_date < datetime('now', 'start of day')\n                ").fetchall()
            return [BorrowRecord(**dict(r)) for r in rows]

    def get_books_with_most_borrow_requests(self) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT b.* \n                FROM books b \n                JOIN borrow_records br ON b.id = br.book_id \n                GROUP BY b.id \n                ORDER BY COUNT(br.id) DESC \n                LIMIT 10\n                ').fetchall()
            return [Book(**dict(r)) for r in rows]

