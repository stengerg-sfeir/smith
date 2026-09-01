"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from book_repository import BookRepository
from database import Database
from exceptions import (
    BookNotAvailableException,
    BookNotFoundError,
    InvalidReturnRequestException,
    MemberNotFoundError,
)
from member_repository import MemberRepository
from models import BorrowRecord


class BookService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)
        self.member_repo = MemberRepository(db)

    def borrow_member(self, member_id: int, book_isbn: str) -> Optional[bool]:
        try:
            member = self.member_repo.get_by_id(member_id)
            if not member:
                raise MemberNotFoundError(f'Member with id {member_id} not found')
            book = self.book_repo.get_by_id(book_isbn)
            if not book:
                raise BookNotFoundError(f'Book with ISBN {book_isbn} not found')
            if not book.available:
                raise BookNotAvailableException(f'Book with ISBN {book_isbn} is not available for borrowing')
            borrow_record = BorrowRecord(book_id=book.id, borrow_date=datetime.datetime.now(), member_id=member_id, return_date=None)
            self.book_repo.update(book.id, {'available': False})
            self.member_repo.create(member)
            self.book_repo.create(borrow_record)
            return True
        except Exception as e:
            raise e

    def return_book(self, id: int) -> Optional[bool]:
        try:
            borrow_record = self.book_repo.get_by_id(id)
            if not borrow_record:
                raise BookNotFoundError(f'Book with ID {id} not found')
            if borrow_record.return_date is not None:
                raise InvalidReturnRequestException(f'Book with ID {id} has already been returned')
            return_date = datetime.date.today()
            borrow_record.return_date = return_date
            book = self.book_repo.get_by_id(borrow_record.book_id)
            if not book:
                raise BookNotFoundError(f'Book with ID {borrow_record.book_id} not found')
            book.available = True
            self.book_repo.update(borrow_record.id, {'return_date': return_date.isoformat()})
            self.book_repo.update(book.id, {'available': True})
            return True
        except Exception:
            return False

