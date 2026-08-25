"""Service layer."""
from __future__ import annotations

import datetime
from typing import List

from author_repository import AuthorRepository
from book_repository import BookRepository
from database import Database
from exceptions import (
    BookNotAvailableError,
    DuplicateEmailError,
    InvalidBookIdError,
    InvalidLoanIdError,
    InvalidMemberIdError,
    InvalidQueryError,
    MemberNotActiveError,
    NotFoundError,
    ValidationError,
)
from loan_repository import LoanRepository
from member_repository import MemberRepository
from models import Book, Loan, Member


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
            raise InvalidMemberIdError(f'Member with id {member_id} not found')
        if not member.is_active:
            raise MemberNotActiveError(f'Member with id {member_id} is inactive and cannot borrow books')
        book = self.book_repo.get_by_id(book_id)
        if not book:
            raise InvalidBookIdError(f'Book with id {book_id} not found')
        if book.available_copies <= 0:
            raise BookNotAvailableError(f'Book with id {book_id} has no available copies')
        loan = Loan(book_id=book_id, member_id=member_id, loan_date=datetime.datetime.now().strftime('%Y-%m-%d'), due_date=(datetime.datetime.now() + datetime.timedelta(days=14)).strftime('%Y-%m-%d'), status='active')
        self.loan_repo.create(loan)
        book.available_copies -= 1
        self.book_repo.update(book_id, {'available_copies': book.available_copies})

    def return_book(self, loan_id: int) -> None:
        loan = self.loan_repo.get_by_id(loan_id)
        if not loan:
            raise InvalidLoanIdError(f'Loan with id {loan_id} not found')
        if loan.status != 'active':
            raise ValidationError(f'Loan with id {loan_id} is not active and cannot be returned')
        loan.status = 'returned'
        loan.return_date = datetime.datetime.now().strftime('%Y-%m-%d')
        self.loan_repo.update(loan_id, {'status': loan.status, 'return_date': loan.return_date})
        book = self.book_repo.get_by_id(loan.book_id)
        if not book:
            raise NotFoundError(f'Book with id {loan.book_id} not found')
        book.available_copies += 1
        self.book_repo.update(loan.book_id, {'available_copies': book.available_copies})

    def get_overdue_loans(self) -> List[Loan]:
        return self.loan_repo.find_overdue_loans()

    def renew_membership(self, member_id: int) -> None:
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise InvalidMemberIdError(f'Member with id {member_id} not found')
        new_membership_date = datetime.datetime.now().strftime('%Y-%m-%d')
        self.member_repo.update(member_id, {'membership_date': new_membership_date})

    def search_books(self, query: str) -> List[Book]:
        if not query:
            raise InvalidQueryError('Search query cannot be empty')
        return self.book_repo.search_books(query)

    def add_book(self, title: str, isbn: str, author_id: int, published_year: int, available_copies: int) -> int:
        book = Book(title=title, isbn=isbn, author_id=author_id, published_year=published_year, available_copies=available_copies)
        return self.book_repo.create(book)

    def list_book(self, author_id: int, available_only: bool) -> List[Book]:
        return self.book_repo.list(author_id=author_id, available_only=available_only)

    def add_member(self, name: str, email: str) -> int:
        existing_member = self.member_repo.find_by_email(email)
        if existing_member:
            raise DuplicateEmailError(f'Email {email} is already registered')
        member = Member(name=name, email=email, is_active=True, membership_date=datetime.datetime.now().strftime('%Y-%m-%d'))
        member_id = self.member_repo.create(member)
        return member_id

    def list_member(self, active_only: bool) -> List[Member]:
        return self.member_repo.list(active_only=active_only)

    def get_member_history(self, member_id: int) -> List[Loan]:
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise InvalidMemberIdError(f'Member with id {member_id} not found')
        return self.member_repo.get_member_loan_history(member_id)

