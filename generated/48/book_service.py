"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from book_repository import BookRepository
from database import Database
from models import Book


class BookService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)

    def add_book(self, title: str, author: str, isbn: str, publication_year: Optional[int] = None, genre: Optional[str] = None, pages: Optional[int] = None) -> bool:
        book = Book(title=title, author=author, isbn=isbn, publication_year=publication_year, genre=genre, pages=pages, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.book_repo.create(book)

    def search_book(self, term: str) -> List[Book]:
        author_matches = self.book_repo.get_books_by_author_like(term)
        genre_matches = self.book_repo.get_books_by_genre_like(term)
        all_matches = set()
        results = []
        for book in author_matches:
            book_id = book.id
            if book_id not in all_matches:
                all_matches.add(book_id)
                results.append(book)
        for book in genre_matches:
            book_id = book.id
            if book_id not in all_matches:
                all_matches.add(book_id)
                results.append(book)
        return results

    def organize_book(self, id: int) -> Dict[str, Any]:
        results = []
        groups = {}
        for row in self.book_repo.list():
            key = (row.author, row.genre)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'author': key[0],
                    'genre': key[1],
                    'count': len(group),
                })
        return results

