"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from book_repository import BookRepository
from database import Database
from exceptions import (
    InvalidSearchQueryError,
)
from models import Book


class BookService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)

    def add_book(self, title: str, author: str, isbn: str, publication_year: int, genre: Optional[str] = None, pages: int = None) -> bool:
        book = Book(title=title, author=author, isbn=isbn, publication_year=publication_year, genre=genre, pages=pages, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.book_repo.create(book)

    def list_book(self, title: Optional[str] = None, author: Optional[str] = None, publication_year: Optional[str] = None, publication_year_end: Optional[str] = None) -> List[Book]:
        return self.book_repo.list(title=title, author=author, publication_year=publication_year, publication_year_end=publication_year_end)

    def update_book(self, id: int, title: Optional[str] = None, author: Optional[str] = None, isbn: Optional[str] = None, publication_year: Optional[int] = None, genre: Optional[str] = None, pages: Optional[int] = None) -> bool:
        data = {k: v for k, v in {'title': title, 'author': author, 'isbn': isbn, 'publication_year': publication_year, 'genre': genre, 'pages': pages}.items() if v is not None}
        return self.book_repo.update(id, data)

    def delete_book(self, id: int) -> bool:
        return self.book_repo.delete(id)

    def search_book(self, term: str) -> List[Book]:
        """
            Search for books by title using partial matching.
        
            Args:
                term: The search term to look for in book titles.
            
            Returns:
                List of Book objects that match the search term.
            
            Raises:
                InvalidSearchQueryError: If the search term is empty or invalid.
            """
        if not term or not term.strip():
            raise InvalidSearchQueryError('Search term cannot be empty or whitespace.')
        matching_books = self.book_repo.search_books_by_title(term.strip())
        return matching_books

