"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from book_repository import BookRepository
from database import Database
from exceptions import (
    BookNotAvailableException,
    BookNotFoundError,
    InvalidLoanException,
    LoanNotFoundError,
    ValidationError,
)
from loan_repository import LoanRepository
from member_repository import MemberRepository
from models import Book, Member


class LoanService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)
        self.loan_repo = LoanRepository(db)
        self.member_repo = MemberRepository(db)

    def add_book(self, title: str, author: str, isbn: str, available_copies: int) -> None:
        book = Book(title=title, author=author, isbn=isbn, available_copies=available_copies, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.book_repo.create(book)

    def delete_book(self, id: int) -> None:
        return self.book_repo.delete(id)

    def list_book(self, title: Optional[str] = None, author: Optional[str] = None, isbn: Optional[str] = None, available_copies: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.book_repo.list(title=title, author=author, isbn=isbn, available_copies=available_copies):
            key = (row.title, row.author, row.isbn, row.available_copies)
            groups[key] = groups.get(key, 0) + 1
        for key, count in groups.items():
            results.append({
                    'title': key[0],
                    'author': key[1],
                    'isbn': key[2],
                    'available_copies': key[3],
                    'count': count,
                })
        return results

    def add_member(self, name: str, email: str, phone: Optional[str] = None, membership_since: Optional[str] = None) -> None:
        member = Member(name=name, email=email, phone=phone, membership_since=membership_since, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.member_repo.create(member)

    def list_member(self, name: Optional[str] = None, email: Optional[str] = None, membership_since: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.member_repo.list(name=name, email=email, membership_since=membership_since):
            key = (row.name, row.email)
            groups[key] = groups.get(key, 0) + 1
        for key, count in groups.items():
            results.append({
                    'name': key[0],
                    'email': key[1],
                    'count': count,
                })
        return results

    def loan_member(self, id: int) -> None:
        book = self.book_repo.get_by_id(id)
        if not book:
            raise BookNotFoundError(f'Book with ID {id} not found')
        if book.available_copies <= 0:
            raise BookNotAvailableException(f'Book with ID {id} is not available for borrowing')
        raise ValidationError('Member ID is required to loan a book')

    def return_book(self, id: int) -> None:
        loan = self.loan_repo.get_by_id(id)
        if not loan:
            raise LoanNotFoundError(f'Loan with ID {id} not found')
        if loan.is_returned:
            raise InvalidLoanException(f'Loan with ID {id} is already returned')
        loan.updated_at = datetime.datetime.now()
        loan.is_returned = True
        loan.return_date = datetime.datetime.now()
        self.loan_repo.update(id, {'is_returned': True, 'return_date': datetime.datetime.now(), 'updated_at': datetime.datetime.now()})
        book_id = loan.book_id
        book = self.book_repo.get_by_id(book_id)
        if not book:
            raise BookNotFoundError(f'Book with ID {book_id} not found')
        new_available_copies = book.available_copies + 1
        if new_available_copies < 0:
            raise ValidationError('Cannot have negative available copies')
        self.book_repo.update(book_id, {'available_copies': new_available_copies})

    def check_book(self, id: int) -> Dict[str, Any]:
        book = self.book_repo.get_by_id(id)
        if not book:
            raise BookNotFoundError(f'Book with ID {id} not found')
        if book.available_copies <= 0:
            return {'available': False, 'available_copies': book.available_copies, 'message': 'No copies available for borrowing'}
        loans = self.loan_repo.get_loans_by_book_id(book_id=book.id)
        active_loans = [loan for loan in loans if not loan.is_returned]
        if active_loans:
            return {'available': False, 'available_copies': book.available_copies, 'active_loans_count': len(active_loans), 'message': f'Book is currently borrowed by {len(active_loans)} member(s)'}
        return {'available': True, 'available_copies': book.available_copies, 'message': 'Book is available for borrowing'}

