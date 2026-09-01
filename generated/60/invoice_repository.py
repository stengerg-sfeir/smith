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
                "INSERT INTO invoices (order_id, total_amount, created_at) VALUES (?, ?, ?)",
                (invoice.order_id, invoice.total_amount, invoice.created_at),
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

    def list(self, order_id: Optional[Any] = None, total_amount: Optional[Any] = None, created_at: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Invoice]:
        with self.db.connect() as conn:
            query = "SELECT * FROM invoices WHERE 1=1"
            params: List[Any] = []
            if order_id is not None:
                query += ' AND order_id = ?'
                params.append(order_id)
            if total_amount is not None:
                query += ' AND total_amount >= ?'
                params.append(total_amount)
            if created_at is not None:
                query += ' AND created_at = ?'
                params.append(created_at)
            if start_date is not None:
                query += ' AND created_at >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND created_at <= ?'
                params.append(end_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Invoice(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['order_id', 'total_amount', 'created_at']
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

    def get_invoices_by_customer_id(self, customer_id: int, status_filter: str, date_from: datetime, date_to: datetime) -> list[dict]:
        return []

    def get_invoice_count_by_status(self, date_from: datetime, date_to: datetime) -> dict:
        return {}

    def get_total_invoice_value_by_status(self, date_from: datetime, date_to: datetime) -> dict:
        return {}

    def get_invoices_with_order_details(self, invoice_id: int) -> list[dict]:
        return []

    def get_invoices_with_customer_and_product_details(self, invoice_id: int) -> dict:
        return {}

    def get_invoices_by_date_range_and_status(self, status: str, date_from: datetime, date_to: datetime) -> list[dict]:
        return []

    def get_invoice_summary_by_customer(self, customer_id: int, date_from: datetime, date_to: datetime) -> dict:
        return {}

    def get_invoices_with_product_sales_trend(self, invoice_id: int, start_date: datetime, end_date: datetime, interval: str) -> list[dict]:
        return []

    def get_invoices_by_product_category(self, category_id: int, date_from: datetime, date_to: datetime) -> list[dict]:
        return []

    def get_low_invoice_value_alerts(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM invoices WHERE total_amount < 10.0').fetchall()
            return [Invoice(**dict(r)) for r in rows]

