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
                "INSERT INTO books (title, author, isbn, publication_year, genre, pages, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (book.title, book.author, book.isbn, book.publication_year, book.genre, book.pages, book.created_at, book.updated_at),
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

    def list(self, title: Optional[Any] = None, author: Optional[Any] = None, publication_year: Optional[Any] = None, publication_year_end: Optional[Any] = None, genre: Optional[Any] = None, isbn: Optional[Any] = None, pages: Optional[Any] = None, max_pages: Optional[Any] = None, min_pages: Optional[Any] = None) -> List[Book]:
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
            if genre is not None:
                query += ' AND genre = ?'
                params.append(genre)
            if isbn is not None:
                query += ' AND isbn = ?'
                params.append(isbn)
            if pages is not None:
                query += ' AND pages = ?'
                params.append(pages)
            if max_pages is not None:
                query += ' AND pages <= ?'
                params.append(max_pages)
            if min_pages is not None:
                query += ' AND pages >= ?'
                params.append(min_pages)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Book(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'author', 'isbn', 'publication_year', 'genre', 'pages', 'created_at', 'updated_at']
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

    def search_books_by_title(self, title: str) -> list[Book]:
        return self.list(
            title=title,
        )

    def get_total_books_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM books",
            ).fetchone()
            return int(row["n"])

    def get_books_by_genre(self, genre: str) -> list[Book]:
        return self.list(
            genre=genre,
        )

    def get_books_by_author(self, author: str) -> list[Book]:
        return self.list(
            author=author,
        )

    def get_books_by_publication_year_range(self, start_year: int, end_year: int) -> list[Book]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM books WHERE publication_year BETWEEN ? AND ?', (str(start_year), str(end_year)))
            rows = cursor.fetchall()
            return [Book(**dict(r)) for r in rows]

    def get_books_with_page_count_range(self, min_pages: int, max_pages: int) -> list[Book]:
        return self.list(
            min_pages=min_pages,
            max_pages=max_pages,
        )

    def generate_genre_distribution_report(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT genre, COUNT(*) as count FROM books GROUP BY genre')
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    def get_most_popular_author(self) -> str:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT author FROM books GROUP BY author ORDER BY COUNT(*) DESC LIMIT 1')
            row = cursor.fetchone()
            return row[0] if row else ''

    def get_books_with_isbn_prefix(self, isbn_prefix: str) -> list[Book]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM books WHERE isbn LIKE ?",
                ("%" + isbn_prefix + "%",)
            ).fetchall()
            return [Book(**dict(r)) for r in rows]

