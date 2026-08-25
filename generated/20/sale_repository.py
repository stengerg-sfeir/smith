"""SaleRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Sale


class SaleRepository:
    """SQLite repository for Sale over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, sale: Sale) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sales (product_id, quantity, sale_date) VALUES (?, ?, ?)",
                (sale.product_id, sale.quantity, sale.sale_date),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Sale]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sales WHERE id = ?", (id,)
            ).fetchone()
            return Sale(**dict(row)) if row else None

    def get_all(self) -> List[Sale]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sales ORDER BY id"
            ).fetchall()
            return [Sale(**dict(r)) for r in rows]

    def list(self, product_id: Optional[Any] = None, sale_date_from: Optional[Any] = None, sale_date_to: Optional[Any] = None, quantity: Optional[Any] = None, sale_date: Optional[Any] = None) -> List[Sale]:
        with self.db.connect() as conn:
            query = "SELECT * FROM sales WHERE 1=1"
            params: List[Any] = []
            if product_id is not None:
                query += ' AND product_id = ?'
                params.append(product_id)
            if sale_date_from is not None:
                query += ' AND sale_date >= ?'
                params.append(sale_date_from)
            if sale_date_to is not None:
                query += ' AND sale_date <= ?'
                params.append(sale_date_to)
            if quantity is not None:
                query += ' AND quantity = ?'
                params.append(quantity)
            if sale_date is not None:
                query += ' AND sale_date = ?'
                params.append(sale_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Sale(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['product_id', 'quantity', 'sale_date']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE sales SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM sales WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_sales_report_by_product(self, product_id: int) -> dict:
        return self.list(
            product_id=product_id,
        )

    def get_total_sales_amount(self) -> float:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT SUM(quantity * price) AS total FROM sales JOIN products ON sales.product_id = products.id', ()).fetchall()
            total = rows[0][0] if rows else 0
            return float(total)

    def get_sales_count_per_product(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT products.name, COUNT(sales.id) AS count FROM sales JOIN products ON sales.product_id = products.id GROUP BY products.name', ()).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_sales_with_product_names(self, start_date: str, end_date: str) -> list:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT sales.id, sales.product_id, sales.quantity, sales.sale_date FROM sales JOIN products ON sales.product_id = products.id WHERE sales.sale_date BETWEEN ? AND ?', (start_date, end_date)).fetchall()
            return [Sale(**dict(r)) for r in rows]

