"""InvoiceRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import InvoiceNotFoundError
from models import Invoice, Payment


class InvoiceRepository:
    """SQLite repository for Invoice over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, invoice: Invoice) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO invoices (client_id, invoice_number, due_date, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (invoice.client_id, invoice.invoice_number, invoice.due_date, invoice.amount, invoice.status, invoice.created_at, invoice.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Invoice]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE id = ?", (id,)
            ).fetchone()
            return Invoice(**dict(row)) if row else None

    def get_all(self) -> List[Invoice]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM invoices ORDER BY id"
            ).fetchall()
            return [Invoice(**dict(r)) for r in rows]

    def list(self, invoice_number: Optional[Any] = None, due_date: Optional[Any] = None, amount: Optional[Any] = None, status: Optional[Any] = None, client_id: Optional[Any] = None, max_amount: Optional[Any] = None) -> List[Invoice]:
        with self.db.connect() as conn:
            query = "SELECT * FROM invoices WHERE 1=1"
            params: List[Any] = []
            if invoice_number is not None:
                query += ' AND invoice_number = ?'
                params.append(invoice_number)
            if due_date is not None:
                query += ' AND due_date >= ?'
                params.append(due_date)
            if amount is not None:
                query += ' AND amount >= ?'
                params.append(amount)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if client_id is not None:
                query += ' AND client_id = ?'
                params.append(client_id)
            if max_amount is not None:
                query += ' AND amount <= ?'
                params.append(max_amount)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Invoice(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['client_id', 'invoice_number', 'due_date', 'amount', 'status', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE invoices SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise InvoiceNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM invoices WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_invoices_by_client_and_status(self, client_id: int, status: str) -> list[Invoice]:
        return self.list(
            client_id=client_id,
            status=status,
        )

    def get_invoices_with_payment_status(self, invoice_id: int, payment_status: str) -> list[Payment]:
        with self.db.connect() as conn:
            cursor = conn.execute('SELECT * FROM payments WHERE invoice_id = ? AND status = ?', (invoice_id, payment_status))
            rows = cursor.fetchall()
            return [Payment(**dict(r)) for r in rows]

    def get_outstanding_invoices_by_date_range(self, start_date: date, end_date: date) -> list[Invoice]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM invoices WHERE due_date >= ? AND due_date <= ?", ((start_date, end_date))
            ).fetchall()
            return [Invoice(**dict(r)) for r in rows]

    def get_invoices_overdue_by_client(self, client_id: int, due_date_cutoff: date) -> list[Invoice]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM invoices r JOIN clients o ON r.client_id = o.id WHERE o.id = ?",
                (client_id,)
            ).fetchall()
            return [Invoice(**dict(r)) for r in rows]

    def get_total_outstanding_amount_by_client(self, client_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS v FROM invoices WHERE client_id = ?",
                (client_id,)
            ).fetchone()
            return float(row["v"])

    def get_invoices_with_partial_payments(self, invoice_id: int) -> list[Payment]:
        with self.db.connect() as conn:
            cursor = conn.execute('SELECT * FROM payments WHERE invoice_id = ?', (invoice_id,))
            rows = cursor.fetchall()
            return [Payment(**dict(r)) for r in rows]

    def get_invoices_with_due_date_in_range(self, start_date: date, end_date: date) -> list[Invoice]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM invoices WHERE due_date >= ? AND due_date <= ?", ((start_date, end_date))
            ).fetchall()
            return [Invoice(**dict(r)) for r in rows]

    def get_invoices_by_amount_range(self, min_amount: float, max_amount: float) -> list[Invoice]:
        return self.list(
            amount=min_amount,
            max_amount=max_amount,
        )


    def get_invoices_by_status(self, status: str) -> List[Invoice]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM invoices WHERE status = ?", (status,)
            ).fetchall()
            return [Invoice(**dict(r)) for r in rows]

