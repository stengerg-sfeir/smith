"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from book_repository import BookRepository
from database import Database
from models import Book


class BookService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)

    def add_book(self, title: str, author: str, isbn: str, publication_year: int) -> None:
        book = Book(title=title, author=author, isbn=isbn, publication_year=publication_year)
        return self.book_repo.create(book)

    def list_book(self, title: Optional[str] = None, author: Optional[str] = None, publication_year: Optional[str] = None, publication_year_end: Optional[str] = None) -> List[Book]:
        return self.book_repo.list(title=title, author=author, publication_year=publication_year, publication_year_end=publication_year_end)

    def update_book(self, id: int, title: Optional[str] = None, author: Optional[str] = None, isbn: Optional[str] = None, publication_year: Optional[int] = None) -> None:
        data = {k: v for k, v in {'title': title, 'author': author, 'isbn': isbn, 'publication_year': publication_year}.items() if v is not None}
        return self.book_repo.update(id, data)

    def search_book(self, term: str) -> List[Book]:
        """
            Search for books by title or ISBN containing the given term.
        
            Args:
                term: The search term to look for in titles or ISBNs.
            
            Returns:
                A list of Book objects that match the search term in title or ISBN.
            """
        return self.book_repo.search_books_by_isbn_or_title(search_term=term)

    def delete_book(self, id: int) -> None:
        return self.book_repo.delete(id)

