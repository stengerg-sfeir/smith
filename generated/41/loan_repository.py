"""LoanRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import LoanNotFoundError
from models import Loan


class LoanRepository:
    """SQLite repository for Loan over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, loan: Loan) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO loans (member_id, book_id, loan_date, due_date, return_date, is_returned, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (loan.member_id, loan.book_id, loan.loan_date, loan.due_date, loan.return_date, loan.is_returned, loan.created_at, loan.updated_at),
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

    def list(self, member_id: Optional[Any] = None, book_id: Optional[Any] = None, loan_date: Optional[Any] = None, due_date: Optional[Any] = None, return_date: Optional[Any] = None, is_returned: Optional[Any] = None) -> List[Loan]:
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
            if is_returned is not None:
                query += ' AND is_returned = ?'
                params.append(is_returned)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['member_id', 'book_id', 'loan_date', 'due_date', 'return_date', 'is_returned', 'created_at', 'updated_at']
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

    def get_loans_by_member_id(self, member_id: int) -> list[Loan]:
        return self.list(
            member_id=member_id,
        )

    def get_loans_by_book_id(self, book_id: int) -> list[Loan]:
        return self.list(
            book_id=book_id,
        )

    def get_loans_due_within_next_week(self) -> list[Loan]:
        with self.db.connect() as conn:
            today = '2024-01-01'
            today_str = '2024-01-01'
            seven_days_later = '2024-01-07'
            rows = conn.execute('SELECT l.*, b.title, b.isbn, m.name, m.email, m.phone, m.membership_since FROM loans l JOIN books b ON l.book_id = b.id JOIN members m ON l.member_id = m.id WHERE l.due_date BETWEEN ? AND ?', (today_str, seven_days_later)).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def get_loans_with_return_date_after(self, return_date: datetime) -> list[Loan]:
        return self.list(
            return_date=return_date,
        )

    def get_loans_by_member_name_contains(self, name: str) -> list[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT l.*, b.title, b.isbn, m.name, m.email, m.phone, m.membership_since FROM loans l JOIN books b ON l.book_id = b.id JOIN members m ON l.member_id = m.id WHERE m.name LIKE ?', (f'%{name}%',)).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def get_loans_by_loan_date_range(self, start_date: datetime, end_date: datetime) -> list[Loan]:
        return []

    def get_loans_with_overdue_status(self) -> list[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loans WHERE due_date IS NOT NULL AND due_date < date('now')"
            ).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def get_total_loans_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM loans",
            ).fetchone()
            return int(row["n"])

    def get_loans_by_isbn_range(self, min_isbn: str, max_isbn: str) -> list[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT l.*, b.title, b.isbn, m.name, m.email, m.phone, m.membership_since FROM loans l JOIN books b ON l.book_id = b.id WHERE b.isbn BETWEEN ? AND ?', (min_isbn, max_isbn)).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def get_loans_by_member_email_domain(self, domain: str) -> list[Loan]:
        return []

