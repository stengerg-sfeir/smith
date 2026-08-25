"""Service layer."""
from __future__ import annotations

from typing import List

from book_repository import BookRepository
from database import Database
from exceptions import (
    DuplicateISBNException,
    ValidationError,
)
from models import Book


class BookService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)

    def create_book(self, book: Book) -> bool:
        try:
            if not self.validate_isbn_uniqueness(book.isbn):
                raise DuplicateISBNException(f'ISBN {book.isbn} is already in use.')
            self.book_repo.create(book)
            return True
        except Exception as e:
            if isinstance(e, DuplicateISBNException):
                raise e
            raise ValidationError(f'Failed to create book: {str(e)}')

    def list_all_books(self) -> List[Book]:
        return self.book_repo.get_all()

    def update_book(self, book: Book) -> bool:
        data = {k: v for k, v in {}.items() if v is not None}
        return self.book_repo.update(book, data)

    def delete_book(self, isbn: str) -> bool:
        return self.book_repo.delete(isbn)

    def search_books_by_title_or_isbn(self, search_term: str) -> List[Book]:
        return self.book_repo.search_books_by_isbn_or_title(search_term)

    def get_books_by_author(self, author: str) -> List[Book]:
        return self.book_repo.get_books_by_author(author)

    def get_books_by_publication_year_range(self, start_year: int, end_year: int) -> List[Book]:
        return self.book_repo.get_books_by_publication_year_range(start_year, end_year)

    def get_total_books_count(self) -> int:
        return self.book_repo.get_total_books_count()

    def get_books_with_most_popular_authors(self, top_n: int) -> List[tuple[str, int]]:
        results = {}
        for row in self.book_repo.list():
            key = row.author
            results[key] = results.get(key, 0) + row.publication_year
        return results

    def validate_isbn_uniqueness(self, isbn: str) -> bool:
        existing_book = self.book_repo.get_books_by_isbn(isbn)
        return existing_book is None

