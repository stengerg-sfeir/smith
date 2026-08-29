"""Service layer."""
from __future__ import annotations

import csv
import datetime

from book_repository import BookRepository
from database import Database
from exceptions import (
    BookAlreadyBorrowedException,
    BookNotFoundError,
    InvalidLoanStateException,
    LoanNotFoundError,
    MemberNotFoundError,
    ValidationError,
)
from loan_repository import LoanRepository
from member_repository import MemberRepository
from models import Book, Loan


class LoanService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.book_repo = BookRepository(db)
        self.loan_repo = LoanRepository(db)
        self.member_repo = MemberRepository(db)

    def create_loan(self, member_id: int, book_id: int, loan_date: datetime, due_date: datetime) -> bool:
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise MemberNotFoundError(f'Member with id {member_id} not found')
        book = self.book_repo.get_by_id(book_id)
        if not book:
            raise BookNotFoundError(f'Book with id {book_id} not found')
        if not book.available:
            raise BookAlreadyBorrowedException(f'Book with id {book_id} is not available for borrowing')
        loan = Loan(book_id=book_id, due_date=due_date, loan_date=loan_date, member_id=member_id, status='active')
        try:
            self.loan_repo.create(loan)
            self.book_repo.update(book_id, {'available': False})
            return True
        except Exception as e:
            raise ValidationError(f'Failed to create loan: {str(e)}')

    def close_loan(self, loan_id: int) -> bool:
        loan = self.loan_repo.get_by_id(loan_id)
        if not loan:
            raise LoanNotFoundError(f'Loan with id {loan_id} not found')
        if loan.status != 'active':
            raise InvalidLoanStateException(f'Loan with id {loan_id} is not in active state')
        loan.status = 'returned'
        try:
            self.loan_repo.update(loan_id, {'status': 'returned'})
            book = self.book_repo.get_by_id(loan.book_id)
            if book:
                self.book_repo.update(loan.book_id, {'available': True})
            return True
        except Exception as e:
            raise ValidationError(f'Failed to close loan: {str(e)}')

    def get_available_books(self) -> list[Book]:
        return self.book_repo.get_books_with_active_loans()

    def get_loans_by_member(self, member_id: int) -> list[Loan]:
        return self.loan_repo.get_loans_by_member_and_status(member_id, 'active')

    def get_overdue_loans(self) -> list[Loan]:
        return self.loan_repo.get_loans_with_returned_after_due_date()

    def export_loans_to_csv(self, file_path: str) -> None:
        rows = self.loan_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'member_id', 'book_id', 'loan_date',
                'due_date', 'return_date', 'status',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.member_id, row.book_id, row.loan_date,
                    row.due_date, row.return_date, row.status,
                ])

    def get_books_with_active_loans(self) -> list[Book]:
        return self.book_repo.get_books_with_active_loans()

    def get_total_active_loans_by_book(self) -> dict[int, int]:
        results = {}
        for row in self.loan_repo.list():
            key = row.book_id
            results[key] = results.get(key, 0) + row.book_id
        return results

