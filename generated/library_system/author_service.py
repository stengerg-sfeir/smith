"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from author_repository import AuthorRepository
from book_repository import BookRepository
from database import Database
from exceptions import (
    NotFoundError,
)
from loan_repository import LoanRepository
from member_repository import MemberRepository
from models import Book, Loan, Member


class AuthorService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.author_repo = AuthorRepository(db)
        self.book_repo = BookRepository(db)
        self.loan_repo = LoanRepository(db)
        self.member_repo = MemberRepository(db)

    def add(self, title: str, isbn: str, author_id: str, published_year: str, copies: str) -> None:
        return None

    def list(self, author: Optional[str] = None, available_only: bool = None) -> List[Book]:
        return []

    def search(self, query: str) -> List[Book]:
        """
            Search for books by title or author name using a query string.
            The search is case-insensitive and matches partial titles or author names.
            """
        results = self.book_repo.search_books(query)
        return results

    def add(self, name: str, email: str) -> None:
        return None

    def list(self, active_only: bool) -> List[Member]:
        return []

    def add_book(self, title: str, isbn: str, author_id: int, published_year: int, available_copies: int) -> int:
        book = Book(title=title, isbn=isbn, author_id=author_id, published_year=published_year, available_copies=available_copies)
        return self.book_repo.create(book)

    def list_book(self, author_id: int, available_only: bool) -> List[Book]:
        return self.book_repo.list(author_id=author_id, available_only=available_only)

    def get_member_history(self, member_id: int) -> List[Loan]:
        """
            Retrieves the loan history for a specific member.
        
            Args:
                member_id: The ID of the member to retrieve loan history for.
            
            Returns:
                A list of Loan objects representing the loan history of the member.
            
            Raises:
                NotFoundError: If the member is not found.
            """
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise NotFoundError(f'Member with ID {member_id} not found.')
        return self.member_repo.get_member_loan_history(member_id)

