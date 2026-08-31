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

    def get_loans_by_member(self, member_id: int) -> list[Loan]:
        return self.list(
            member_id=member_id,
        )

    def get_loans_by_book(self, book_id: int) -> list[Loan]:
        return self.list(
            book_id=book_id,
        )

    def get_active_loans_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM loans",
            ).fetchone()
            return int(row["n"])

    def get_overdue_loans(self) -> list[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loans WHERE due_date IS NOT NULL AND due_date < date('now')"
            ).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def get_loans_with_status(self, status: str) -> list[Loan]:
        return self.list(
            status=status,
        )

    def get_available_books_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM loans",
            ).fetchone()
            return int(row["n"])

    def get_loans_by_date_range(self, start_date: datetime, end_date: datetime) -> list[Loan]:
        return []

    def get_total_loans_by_member(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT m.name, COUNT(l.id) AS loan_count FROM loans l JOIN members m ON l.member_id = m.id GROUP BY m.id, m.name').fetchall()
        result: dict[str, int] = {}
        for row in rows:
            result[row[0]] = row[1]
        return result

    def get_loans_with_return_date_after(self, return_date: datetime) -> list[Loan]:
        return self.list(
            return_date=return_date,
        )

