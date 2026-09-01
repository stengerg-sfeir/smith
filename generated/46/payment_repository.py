"""PaymentRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import PaymentNotFoundError
from models import Payment


class PaymentRepository:
    """SQLite repository for Payment over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, payment: Payment) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO payments (invoice_id, amount, payment_date, method, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (payment.invoice_id, payment.amount, payment.payment_date, payment.method, payment.status, payment.created_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Payment]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE id = ?", (id,)
            ).fetchone()
            return Payment(**dict(row)) if row else None

    def get_all(self) -> List[Payment]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM payments ORDER BY id"
            ).fetchall()
            return [Payment(**dict(r)) for r in rows]

    def list(self, payment_date: Optional[Any] = None, amount: Optional[Any] = None, method: Optional[Any] = None, status: Optional[Any] = None, invoice_id: Optional[Any] = None, max_amount: Optional[Any] = None) -> List[Payment]:
        with self.db.connect() as conn:
            query = "SELECT * FROM payments WHERE 1=1"
            params: List[Any] = []
            if payment_date is not None:
                query += ' AND payment_date >= ?'
                params.append(payment_date)
            if amount is not None:
                query += ' AND amount >= ?'
                params.append(amount)
            if method is not None:
                query += ' AND method = ?'
                params.append(method)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if invoice_id is not None:
                query += ' AND invoice_id = ?'
                params.append(invoice_id)
            if max_amount is not None:
                query += ' AND amount <= ?'
                params.append(max_amount)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Payment(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['invoice_id', 'amount', 'payment_date', 'method', 'status', 'created_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE payments SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise PaymentNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM payments WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_payments_by_client_and_date_range(self, client_id: int, start_date: date, end_date: date) -> list[Payment]:
        return []

    def get_payments_by_invoice_status(self, invoice_id: int, status: str) -> list[Payment]:
        return self.list(
            invoice_id=invoice_id,
            status=status,
        )

    def get_total_payments_by_client(self, client_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute('SELECT SUM(amount) FROM payments WHERE invoice_id IN (SELECT id FROM invoices WHERE client_id = ?)', (client_id,)).fetchone()
        return row[0] if row[0] is not None else 0.0

    def get_payments_with_partial_amounts(self, invoice_id: int) -> list[Payment]:
        return self.list(
            invoice_id=invoice_id,
        )

    def get_payment_summary_by_date_range(self, start_date: date, end_date: date) -> dict:
        return {}

    def get_latest_payment_for_invoice(self, invoice_id: int) -> Optional[Payment]:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM payments WHERE invoice_id = ? ORDER BY payment_date DESC LIMIT 1', (invoice_id,)).fetchone()
        return Payment(**dict(row)) if row else None

    def get_payments_overdue_by_client(self, client_id: int, due_date_cutoff: date) -> list[Payment]:
        return []

