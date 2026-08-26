"""InvoiceRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import InvoiceNotFoundError
from models import Invoice


class InvoiceRepository:
    """SQLite repository for Invoice over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, invoice: Invoice) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO invoices (customer_id, total_amount, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (invoice.customer_id, invoice.total_amount, invoice.created_at, invoice.updated_at),
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

    def list(self, customer_id: Optional[Any] = None, total_amount: Optional[Any] = None, created_at: Optional[Any] = None) -> List[Invoice]:
        with self.db.connect() as conn:
            query = "SELECT * FROM invoices WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if total_amount is not None:
                query += ' AND total_amount >= ?'
                params.append(total_amount)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Invoice(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'total_amount', 'created_at', 'updated_at']
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
            cur.execute("DELETE FROM invoices WHERE id = ?", (id,))
            conn.commit()
            return cur.rowcount > 0
