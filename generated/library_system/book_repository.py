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
                "INSERT INTO books (title, isbn, published_year, available_copies) VALUES (?, ?, ?, ?)",
                (book.title, book.isbn, book.published_year, book.available_copies),
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

    def list(self, title: Optional[Any] = None, available_copies: Optional[Any] = None, isbn: Optional[Any] = None) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if available_copies is not None:
                query += ' AND available_copies >= ?'
                params.append(available_copies)
            if isbn is not None:
                query += ' AND isbn = ?'
                params.append(isbn)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Book(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'isbn', 'published_year', 'available_copies']
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
        return self.list(isbn=isbn)

    def find_by_title(self, title: str) -> Optional[Book]:
        return self.list(title=title)

    def find_by_author(self, author_id: int) -> List[Book]:
        with self.db.connect() as conn:
            # Assuming there's a junction table or books have author_id field
            # This implementation assumes a books_authors junction table
            query = "SELECT b.* FROM books b JOIN books_authors ba ON b.id = ba.book_id WHERE ba.author_id = ?"
            rows = conn.execute(query, (author_id,)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def filter_by_available_copies(self, min_copies: int, max_copies: int) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books WHERE available_copies >= ? AND available_copies <= ? ORDER BY available_copies"
            rows = conn.execute(query, (min_copies, max_copies)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def search_books(self, query: str) -> List[Book]:
        with self.db.connect() as conn:
            # Case-insensitive search on title and isbn
            query = query.strip()
            if not query:
                return self.get_all()

            # Search in title and isbn fields
            search_query = "SELECT * FROM books WHERE title LIKE ? OR isbn LIKE ? ORDER BY title"
            search_term = f"%{query}%"
            rows = conn.execute(search_query, (search_term, search_term)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_total_available_copies(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute("SELECT SUM(available_copies) FROM books")
            result = cursor.fetchone()
            return result[0] if result[0] is not None else 0

    def get_books_by_year_range(self, start_year: int, end_year: int) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books WHERE published_year >= ? AND published_year <= ? ORDER BY published_year"
            rows = conn.execute(query, (start_year, end_year)).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_with_lowest_copies(self, limit: int) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books ORDER BY available_copies ASC LIMIT ?"
            rows = conn.execute(query, (limit,)).fetchall()
            return [Book(**dict(r)) for r in rows]

