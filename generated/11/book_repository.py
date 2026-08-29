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
                "INSERT INTO books (title, author, isbn, publication_year) VALUES (?, ?, ?, ?)",
                (book.title, book.author, book.isbn, book.publication_year),
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

    def list(self, title: Optional[Any] = None, author: Optional[Any] = None, publication_year: Optional[Any] = None, publication_year_end: Optional[Any] = None, isbn: Optional[Any] = None) -> List[Book]:
        with self.db.connect() as conn:
            query = "SELECT * FROM books WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if author is not None:
                query += ' AND author = ?'
                params.append(author)
            if publication_year is not None:
                query += ' AND publication_year >= ?'
                params.append(publication_year)
            if publication_year_end is not None:
                query += ' AND publication_year <= ?'
                params.append(publication_year_end)
            if isbn is not None:
                query += ' AND isbn = ?'
                params.append(isbn)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Book(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'author', 'isbn', 'publication_year']
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

    def get_books_by_publication_year_range(self, start_year: int, end_year: int) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM books WHERE publication_year >= ? AND publication_year <= ?", ((start_year, end_year))
            ).fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_by_title_contains(self, title_keyword: str) -> list[Book]:
        return []

    def get_total_books_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM books",
            ).fetchone()
            return int(row["n"])

    def get_books_with_most_popular_authors(self, top_n: int) -> list[tuple[str, int]]:
        with self.db.connect() as conn:
            cursor = conn.execute('\n                SELECT author, COUNT(*) as book_count\n                FROM books\n                GROUP BY author\n                ORDER BY book_count DESC\n                LIMIT ?\n            ', (top_n,))
            rows = cursor.fetchall()
            return [(row[0], row[1]) for row in rows]

    def search_books_by_isbn_or_title(self, search_term: str) -> list[Book]:
        return []

    def get_books_by_isbn(self, isbn: str) -> Optional[Book]:
        return self.list(
            isbn=isbn,
        )

