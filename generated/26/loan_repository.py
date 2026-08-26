"""LoanRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import LoanNotFoundError
from models import Book, Loan


class LoanRepository:
    """SQLite repository for Loan over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, loan: Loan) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO loans (member_id, book_id, loan_date, due_date, return_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                (loan.member_id, loan.book_id, loan.loan_date, loan.due_date, loan.return_date, loan.status),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Loan]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM loans WHERE id = ?", (id,)
            ).fetchone()
            return Loan(**dict(row)) if row else None

    def get_all(self) -> List[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loans ORDER BY id"
            ).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def list(self, member_id: Optional[Any] = None, book_id: Optional[Any] = None, loan_date: Optional[Any] = None, due_date: Optional[Any] = None, return_date: Optional[Any] = None, status: Optional[Any] = None) -> List[Loan]:
        with self.db.connect() as conn:
            query = "SELECT * FROM loans WHERE 1=1"
            params: List[Any] = []
            if member_id is not None:
                query += ' AND member_id = ?'
                params.append(member_id)
            if book_id is not None:
                query += ' AND book_id = ?'
                params.append(book_id)
            if loan_date is not None:
                query += ' AND loan_date >= ?'
                params.append(loan_date)
            if due_date is not None:
                query += ' AND due_date >= ?'
                params.append(due_date)
            if return_date is not None:
                query += ' AND return_date >= ?'
                params.append(return_date)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['member_id', 'book_id', 'loan_date', 'due_date', 'return_date', 'status']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE loans SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise LoanNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM loans WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_loans_by_member_and_status(self, member_id: int, status: str) -> list[Loan]:
        return self.list(
            member_id=member_id,
            status=status,
        )

    def get_loans_with_overdue_dates(self) -> list[Loan]:
        raise NotImplementedError()

    def get_books_with_loans_and_due_dates(self) -> list[tuple[Book, Loan]]:
        raise NotImplementedError()

    def get_loans_by_date_range(self, start_date: datetime, end_date: datetime) -> list[Loan]:
        raise NotImplementedError()

    def get_loans_with_return_dates_after(self, return_date_threshold: datetime) -> list[Loan]:
        raise NotImplementedError()

    def get_loans_by_member_and_book_author(self, member_id: int, author: str) -> list[Loan]:
        return self.list(
            member_id=member_id,
        )

    def get_total_active_loans_by_book(self) -> dict[int, int]:
        raise NotImplementedError()

    def get_loans_with_pending_return_status(self) -> list[Loan]:
        raise NotImplementedError()

    def get_loans_with_returned_after_due_date(self) -> list[Loan]:
        raise NotImplementedError()

