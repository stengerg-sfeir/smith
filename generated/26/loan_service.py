"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, Optional

from book_repository import BookRepository
from database import Database
from exceptions import (
    BookAlreadyBorrowedException,
    BookNotFoundError,
)
from loan_repository import LoanRepository
from member_repository import MemberRepository
from models import Member


class LoanService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)
        self.loan_repo = LoanRepository(db)
        self.member_repo = MemberRepository(db)

    def add_member(self, name: str, email: str, phone: Optional[str] = None) -> bool:
        member = Member(name=name, email=email, phone=phone)
        return self.member_repo.create(member)

    def close_book(self, id: int) -> bool:
        """Closes a book by setting its available status to False.
        
            A book can only be closed if it is not currently borrowed.
            If the book is already borrowed, this method raises BookAlreadyBorrowedException.
        
            Args:
                id: The ID of the book to close.
            
            Returns:
                True if the book was successfully closed, False otherwise.
            """
        try:
            book = self.book_repo.get_by_id(id)
            if not book:
                raise BookNotFoundError(f'Book with ID {id} not found')
            loans = self.loan_repo.get_loans_by_book(book.id)
            if loans:
                raise BookAlreadyBorrowedException(f'Book with ID {id} is currently borrowed and cannot be closed')
            book.available = False
            self.book_repo.update(id, {'available': False})
            return True
        except Exception as e:
            raise e

    def check_book(self, id: int) -> Dict[str, Any]:
        results = []
        groups = {}
        for row in self.book_repo.list():
            key = (row.id)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'id': key[0],
                    'count': len(group),
                })
        return results

