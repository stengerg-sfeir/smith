"""LoanRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Loan


class LoanRepository:
    """SQLite repository for Loan over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, loan: Loan) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO loans (book_id, member_id, loan_date, due_date, return_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                (loan.book_id, loan.member_id, loan.loan_date, loan.due_date, loan.return_date, loan.status),
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

    def list(self, status: Optional[Any] = None, due_date: Optional[Any] = None, return_date: Optional[Any] = None, book_id: Optional[Any] = None, member_id: Optional[Any] = None) -> List[Loan]:
        with self.db.connect() as conn:
            query = "SELECT * FROM loans WHERE 1=1"
            params: List[Any] = []
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if due_date is not None:
                query += ' AND due_date >= ?'
                params.append(due_date)
            if return_date is not None:
                query += ' AND return_date >= ?'
                params.append(return_date)
            if book_id is not None:
                query += ' AND book_id = ?'
                params.append(book_id)
            if member_id is not None:
                query += ' AND member_id = ?'
                params.append(member_id)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['book_id', 'member_id', 'loan_date', 'due_date', 'return_date', 'status']
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
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM loans WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def find_active_loans(self, member_id: Optional[int] = None, book_id: Optional[int] = None) -> List[Loan]:
        return self.list(
            member_id=member_id,
            book_id=book_id,
        )

    def find_overdue_loans(self) -> List[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loans WHERE due_date IS NOT NULL AND due_date < date('now')"
            ).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def find_by_member_id(self, member_id: int) -> List[Loan]:
        return self.list(
            member_id=member_id,
        )

    def find_by_book_id(self, book_id: int) -> List[Loan]:
        return self.list(
            book_id=book_id,
        )

    def get_total_active_loans(self) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM loans WHERE status = ?', ('active',)).fetchone()
            return rows[0] if rows else 0

    def get_total_overdue_loans(self) -> int:
        return 0

    def get_loans_by_status(self, status: str) -> List[Loan]:
        return self.list(
            status=status,
        )

    def get_loans_with_return_date_range(self, start_date: datetime, end_date: datetime) -> List[Loan]:
        return []

    def get_loans_by_member_and_book(self, member_id: int, book_id: int) -> List[Loan]:
        return self.list(
            member_id=member_id,
            book_id=book_id,
        )

    def get_loan_history_for_member(self, member_id: int) -> List[Loan]:
        return self.list(
            member_id=member_id,
        )

    def get_book_loan_history(self, book_id: int) -> List[Loan]:
        return self.list(
            book_id=book_id,
        )

    def get_loans_with_due_date_range(self, start_date: datetime, end_date: datetime) -> List[Loan]:
        return []

