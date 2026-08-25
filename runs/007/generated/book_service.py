"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List

from book_repository import BookRepository
from database import Database
from exceptions import (
    BookAlreadyExistsError,
    InvalidSearchQueryError,
)
from models import Book


class BookService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)

    def create_book(self, book: Book) -> bool:
        try:
            self.book_repo.create(book)
            return True
        except BookAlreadyExistsError:
            return False

    def list_books(self) -> List[Book]:
        return self.book_repo.list()

    def update_book(self, book: Book) -> bool:
        data = {k: v for k, v in {}.items() if v is not None}
        return self.book_repo.update(book, data)

    def delete_book(self, book_id: int) -> bool:
        return self.book_repo.delete(book_id)

    def search_books_by_title(self, title: str) -> List[Book]:
        try:
            return self.book_repo.search_books_by_title(title)
        except InvalidSearchQueryError as e:
            raise e

    def get_total_books_count(self) -> int:
        return self.book_repo.get_total_books_count()

    def get_books_by_genre(self, genre: str) -> List[Book]:
        return self.book_repo.get_books_by_genre(genre)

    def get_books_by_author(self, author: str) -> List[Book]:
        return self.book_repo.get_books_by_author(author)

    def get_books_by_publication_year_range(self, start_year: int, end_year: int) -> List[Book]:
        return self.book_repo.get_books_by_publication_year_range(start_year, end_year)

    def get_books_with_page_count_range(self, min_pages: int, max_pages: int) -> List[Book]:
        return self.book_repo.get_books_with_page_count_range(min_pages, max_pages)

    def generate_genre_distribution_report(self) -> Dict[str, int]:
        results = {}
        for row in self.book_repo.list():
            key = row.genre
            results[key] = results.get(key, 0) + row.pages
        return results

    def get_most_popular_author(self) -> str:
        return self.book_repo.get_most_popular_author()

    def get_books_with_isbn_prefix(self, isbn_prefix: str) -> List[Book]:
        return self.book_repo.get_books_with_isbn_prefix(isbn_prefix)

    def add_book(self, title: str, author: str, isbn: str, publication_year: int, genre: str, pages: int) -> int:
        book = Book(title=title, author=author, isbn=isbn, publication_year=publication_year, genre=genre, pages=pages, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.book_repo.create(book)

