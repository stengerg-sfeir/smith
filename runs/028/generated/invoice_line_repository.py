"""InvoiceLineRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import InvoiceLine


class InvoiceLineRepository:
    """SQLite repository for InvoiceLine over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, invoice_line: InvoiceLine) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO invoicelines (invoice_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                (invoice_line.invoice_id, invoice_line.product_id, invoice_line.quantity, invoice_line.unit_price),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[InvoiceLine]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM invoicelines WHERE id = ?", (id,)
            ).fetchone()
            return InvoiceLine(**dict(row)) if row else None

    def get_all(self) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM invoicelines ORDER BY id"
            ).fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def list(self, invoice_id: Optional[Any] = None, product_id: Optional[Any] = None, quantity: Optional[Any] = None, unit_price: Optional[Any] = None, max_quantity: Optional[Any] = None, max_unit_price: Optional[Any] = None) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            query = "SELECT * FROM invoicelines WHERE 1=1"
            params: List[Any] = []
            if invoice_id is not None:
                query += ' AND invoice_id = ?'
                params.append(invoice_id)
            if product_id is not None:
                query += ' AND product_id = ?'
                params.append(product_id)
            if quantity is not None:
                query += ' AND quantity >= ?'
                params.append(quantity)
            if unit_price is not None:
                query += ' AND unit_price >= ?'
                params.append(unit_price)
            if max_quantity is not None:
                query += ' AND quantity <= ?'
                params.append(max_quantity)
            if max_unit_price is not None:
                query += ' AND unit_price <= ?'
                params.append(max_unit_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['invoice_id', 'product_id', 'quantity', 'unit_price']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE invoicelines SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM invoicelines WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_invoice_lines_by_invoice_id(self, invoice_id: int) -> List[InvoiceLine]:
        return self.list(
            invoice_id=invoice_id,
        )

    def get_invoice_lines_by_product_id(self, product_id: int, start_date: datetime, end_date: datetime) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM invoicelines r JOIN products o ON r.product_id = o.id WHERE o.id = ?",
                (product_id,)
            ).fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def get_invoice_lines_with_quantity_range(self, min_quantity: int, max_quantity: int) -> List[InvoiceLine]:
        return self.list(
            quantity=min_quantity,
            max_quantity=max_quantity,
        )

    def get_invoice_lines_by_date_range(self, start_date: datetime, end_date: datetime) -> List[InvoiceLine]:
        return []

    def get_total_invoice_lines_by_product(self, product_id: int, start_date: str, end_date: str) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM invoicelines WHERE product_id = ? AND invoice_id IN (SELECT id FROM invoices WHERE created_at BETWEEN ? AND ?)', (product_id, start_date, end_date)).fetchone()
            return rows[0] if rows else 0

    def get_invoice_lines_with_unit_price_range(self, min_unit_price: float, max_unit_price: float) -> List[InvoiceLine]:
        return self.list(
            unit_price=min_unit_price,
            max_unit_price=max_unit_price,
        )

    def get_invoice_lines_by_customer(self, customer_id: int, start_date: str, end_date: str) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM invoicelines WHERE invoice_id IN (SELECT id FROM invoices WHERE customer_id = ? AND created_at BETWEEN ? AND ?)', (customer_id, start_date, end_date)).fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def get_invoice_lines_summary_by_product(self, start_date: str, end_date: str) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT product_id, SUM(quantity) AS total_quantity FROM invoicelines WHERE invoice_id IN (SELECT id FROM invoices WHERE created_at BETWEEN ? AND ?) GROUP BY product_id', (start_date, end_date)).fetchall()
            result = {}
            for row in rows:
                result[row['product_id']] = row['total_quantity']
            return result

