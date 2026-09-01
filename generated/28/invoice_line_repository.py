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

    def list(self, invoice_id: Optional[Any] = None, product_id: Optional[Any] = None, quantity: Optional[Any] = None, unit_price: Optional[Any] = None, max_price: Optional[Any] = None, max_unit_price: Optional[Any] = None) -> List[InvoiceLine]:
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
            if max_price is not None:
                query += ' AND unit_price <= ?'
                params.append(max_price)
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

    def get_invoice_lines_by_product_id(self, product_id: int, min_quantity: int) -> List[InvoiceLine]:
        return self.list(
            product_id=product_id,
            quantity=min_quantity,
        )

    def get_invoice_lines_with_price_range(self, min_unit_price: float, max_unit_price: float) -> List[InvoiceLine]:
        return self.list(
            unit_price=min_unit_price,
            max_unit_price=max_unit_price,
        )

    def get_invoice_lines_by_customer(self, customer_id: int, created_after: str, created_before: str) -> List[InvoiceLine]:
        with self.db.connect() as conn:
            query = '\n                SELECT il.id, il.invoice_id, il.product_id, il.quantity, il.unit_price\n                FROM invoicelines il\n                JOIN invoices i ON il.invoice_id = i.id\n                WHERE i.customer_id = ?\n                AND i.created_at BETWEEN ? AND ?\n            '
            rows = conn.execute(query, (customer_id, created_after, created_before)).fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

    def get_total_invoice_lines_by_product(self) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT p.id, p.name, SUM(il.quantity) AS total_quantity\n                FROM invoicelines il\n                JOIN products p ON il.product_id = p.id\n                GROUP BY p.id, p.name\n            '
            rows = conn.execute(query).fetchall()
            return {row['name']: row['total_quantity'] for row in rows}

    def get_invoice_lines_with_subtotal_summary(self, product_id: int, min_quantity: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM invoicelines r JOIN products o ON r.product_id = o.id WHERE o.id = ?",
                (product_id,)
            ).fetchall()
            return [InvoiceLine(**dict(r)) for r in rows]

