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

    def list(self, invoice_id: Optional[Any] = None, product_id: Optional[Any] = None, quantity: Optional[Any] = None, unit_price: Optional[Any] = None) -> List[InvoiceLine]:
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
        return self.list(
            product_id=product_id,
        )

    def get_invoice_lines_with_quantity_range(self, min_quantity: int, max_quantity: int) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM invoicelines WHERE quantity BETWEEN ? AND ?', (min_quantity, max_quantity))
            rows = cursor.fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def get_invoice_lines_by_date_range(self, start_date: str, end_date: str) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM invoicelines WHERE invoice_id IN (SELECT id FROM invoices WHERE created_at BETWEEN ? AND ?)', (start_date, end_date))
            rows = cursor.fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def get_total_invoice_lines_by_product(self, product_id: int, start_date: datetime, end_date: datetime) -> int:
        return self.list(
            product_id=product_id,
        )

    def get_invoice_lines_with_unit_price_range(self, min_unit_price: float, max_unit_price: float) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM invoicelines WHERE unit_price BETWEEN ? AND ?', (min_unit_price, max_unit_price))
            rows = cursor.fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def get_invoice_lines_by_customer(self, customer_id: int, start_date: str, end_date: str) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT il.*\n                FROM invoicelines il\n                JOIN invoices i ON il.invoice_id = i.id\n                WHERE i.customer_id = ? AND i.created_at BETWEEN ? AND ?\n                ', (customer_id, start_date, end_date))
            rows = cursor.fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def get_invoice_lines_summary_by_product(self, start_date: str, end_date: str) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT \n                    p.id AS product_id,\n                    p.name AS product_name,\n                    SUM(il.quantity) AS total_quantity,\n                    SUM(il.quantity * il.unit_price) AS total_revenue\n                FROM invoicelines il\n                JOIN products p ON il.product_id = p.id\n                JOIN invoices i ON il.invoice_id = i.id\n                WHERE i.created_at BETWEEN ? AND ?\n                GROUP BY p.id, p.name\n                ', (start_date, end_date))
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                result[row['product_name']] = {'product_id': row['product_id'], 'total_quantity': row['total_quantity'], 'total_revenue': row['total_revenue']}
            return result

