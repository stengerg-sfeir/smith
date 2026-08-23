"""Service layer."""
from __future__ import annotations

import datetime
from typing import List

from author_repository import AuthorRepository
from book_repository import BookRepository
from database import Database
from exceptions import (
    BookNotAvailableError,
    InvalidLoanStatusError,
    MemberNotActiveError,
    NotFoundError,
)
from loan_repository import LoanRepository
from member_repository import MemberRepository
from models import Book, Loan


class LibraryService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.author_repo = AuthorRepository(db)
        self.book_repo = BookRepository(db)
        self.loan_repo = LoanRepository(db)
        self.member_repo = MemberRepository(db)

    def borrow_book(self, member_id: int, book_id: int) -> None:
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise NotFoundError(f'Member with id {member_id} not found')
        if not member.is_active:
            raise MemberNotActiveError(f'Member with id {member_id} is inactive and cannot borrow books')
        book = self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundError(f'Book with id {book_id} not found')
        if book.available_copies <= 0:
            raise BookNotAvailableError(f'Book with id {book_id} has no available copies')
        loan = Loan(book_id=book_id, member_id=member_id, loan_date=datetime.datetime.now().strftime('%Y-%m-%d'), due_date=(datetime.datetime.now() + datetime.timedelta(days=14)).strftime('%Y-%m-%d'), status='active')
        self.loan_repo.create(loan)
        book.available_copies -= 1
        self.book_repo.update(book.id, {'available_copies': book.available_copies})

    def return_book(self, loan_id: int) -> None:
        loan = self.loan_repo.get_by_id(loan_id)
        if not loan:
            raise NotFoundError(f'Loan with id {loan_id} not found')
        if loan.status != 'active':
            raise InvalidLoanStatusError(f'Loan with id {loan_id} is not active and cannot be returned')
        book = self.book_repo.get_by_id(loan.book_id)
        if not book:
            raise NotFoundError(f'Book with id {loan.book_id} not found')
        book.available_copies += 1
        self.book_repo.update(book.id, {'available_copies': book.available_copies})
        loan.status = 'returned'
        loan.return_date = datetime.datetime.now().strftime('%Y-%m-%d')
        self.loan_repo.update(loan_id, {'status': loan.status, 'return_date': loan.return_date})

    def get_overdue_loans(self) -> List[Loan]:
        overdue_loans = self.loan_repo.find_overdue_loans()
        return overdue_loans

    def renew_membership(self, member_id: int) -> None:
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise NotFoundError(f'Member with id {member_id} not found')
        new_membership_date = datetime.datetime.now().strftime('%Y-%m-%d')
        self.member_repo.update(member_id, {'membership_date': new_membership_date})

    def search_books(self, query: str) -> List[Book]:
        results = self.book_repo.search_books(query)
        return results

