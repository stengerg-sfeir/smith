"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from database import Database
from exceptions import (
    BookAlreadyBorrowedException,
    BookNotFoundError,
    InvalidLoanStateException,
    LoanNotFoundError,
    MemberNotFoundError,
)
from loan_repository import LoanRepository
from models import Book, Loan


class LoanService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.loan_repo = LoanRepository(db)

    def create_loan(self, member_id: int, book_id: int, loan_date: datetime, due_date: datetime) -> Optional[Loan]:
        try:
            member = self.loan_repo.get_by_id(member_id)
            if not member:
                raise MemberNotFoundError(f'Member with id {member_id} not found')
        except LoanNotFoundError:
            raise MemberNotFoundError(f'Member with id {member_id} not found')
        try:
            book = self.loan_repo.get_by_id(book_id)
            if not book:
                raise BookNotFoundError(f'Book with id {book_id} not found')
            if not book.available:
                raise BookAlreadyBorrowedException(f'Book with id {book_id} is already borrowed')
        except BookNotFoundError:
            raise BookNotFoundError(f'Book with id {book_id} not found')
        loan = Loan(book_id=book_id, due_date=due_date, loan_date=loan_date, member_id=member_id, status='active')
        created_loan = self.loan_repo.create(loan)
        book.available = False
        self.loan_repo.update(book.id, {'available': False})
        return created_loan

    def close_loan(self, loan_id: int) -> Optional[Loan]:
        try:
            loan = self.loan_repo.get_by_id(loan_id)
            if not loan:
                raise LoanNotFoundError(f'Loan with id {loan_id} not found')
            if loan.status != 'active':
                raise InvalidLoanStateException(f'Loan with id {loan_id} is not in active state')
            loan.status = 'closed'
            updated_loan = self.loan_repo.update(loan.id, {'status': 'closed'})
            return updated_loan
        except Exception as e:
            raise InvalidLoanStateException(f'Cannot close loan: {str(e)}')

    def get_available_books(self) -> List[Book]:
        books = self.loan_repo.get_all()
        available_books = [book for book in books if book.available]
        return available_books

    def get_loans_by_member(self, member_id: int) -> List[Loan]:
        return self.loan_repo.get_loans_by_member(member_id)

    def get_overdue_loans(self) -> List[Loan]:
        today = datetime.datetime.now().date()
        return self.loan_repo.get_overdue_loans()

    def get_total_loans_by_member(self) -> Dict[str, int]:
        return self.loan_repo.get_total_loans_by_member()

    def get_active_loans_count(self) -> int:
        return self.loan_repo.get_active_loans_count()

    def get_loans_with_return_date_after(self, return_date: datetime) -> List[Loan]:
        return self.loan_repo.get_loans_with_return_date_after(return_date)

