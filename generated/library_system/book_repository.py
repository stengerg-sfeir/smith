"""BookRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Book


class BookRepository:
    """SQLite repository for Book over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, book: Book) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO books (title, isbn, published_year, available_copies, author_id) VALUES (?, ?, ?, ?, ?)",
                (book.title, book.isbn, book.published_year, book.available_copies, book.author_id),
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

    def list(self, title: Optional[Any] = None, available_copies: Optional[Any] = None, author_id: Optional[Any] = None, isbn: Optional[Any] = None, published_year: Optional[Any] = None, max_copies: Optional[Any] = None, available_only: Optional[Any] = None) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if available_copies is not None:
                query += ' AND available_copies >= ?'
                params.append(available_copies)
            if author_id is not None:
                query += ' AND author_id = ?'
                params.append(author_id)
            if isbn is not None:
                query += ' AND isbn = ?'
                params.append(isbn)
            if published_year is not None:
                query += ' AND published_year = ?'
                params.append(published_year)
            if max_copies is not None:
                query += ' AND available_copies <= ?'
                params.append(max_copies)
            if available_only:
                query += ' AND available_copies > 0'
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Book(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'isbn', 'published_year', 'available_copies', 'author_id']
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
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM books WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def find_by_isbn(self, isbn: str) -> Optional[Book]:
        return self.list(
            isbn=isbn,
        )

    def find_by_title(self, title: str) -> Optional[Book]:
        return self.list(
            title=title,
        )

    def find_by_author(self, author_id: int) -> List[Book]:
        return self.list(
            author_id=author_id,
        )

    def filter_by_available_copies(self, min_copies: int, max_copies: int) -> List[Book]:
        return self.list(
            available_copies=min_copies,
            max_copies=max_copies,
        )

    def search_books(self, query: str) -> List[Book]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM books WHERE title LIKE ? OR isbn LIKE ?', (f'%{query}%', f'%{query}%'))
            rows = cursor.fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_total_available_copies(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(available_copies) FROM books')
            result = cursor.fetchone()
            return result[0] if result[0] is not None else 0

    def get_books_by_year_range(self, start_year: int, end_year: int) -> List[Book]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM books WHERE published_year BETWEEN ? AND ?', (str(start_year), str(end_year)))
            rows = cursor.fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_with_lowest_copies(self, limit: int) -> List[Book]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM books ORDER BY available_copies ASC LIMIT ?",
                (limit,)
            ).fetchall()
            return [Book(**dict(r)) for r in rows]

