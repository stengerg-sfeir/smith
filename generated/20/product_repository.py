"""ProductRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Product


class ProductRepository:
    """SQLite repository for Product over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, product: Product) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO products (name, price) VALUES (?, ?)",
                (product.name, product.price),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Product]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?", (id,)
            ).fetchone()
            return Product(**dict(row)) if row else None

    def get_all(self) -> List[Product]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY id"
            ).fetchall()
            return [Product(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price = ?'
                params.append(price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'price']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE products SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM products WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_sales_report_by_product(self, product_id: int) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT s.sale_date, s.quantity, p.name, p.price \n                FROM sales s \n                JOIN products p ON s.product_id = p.id \n                WHERE s.product_id = ?\n            '
            conn.execute(query, (product_id,))
            rows = conn.execute(query, (product_id,)).fetchall()
            return {row[3]: {'date': row[0], 'quantity': row[1], 'name': row[2], 'price': row[3]} for row in rows}

    def get_total_sales_amount(self) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(price), 0) AS v FROM products",
            ).fetchone()
            return float(row["v"])

    def get_sales_count_per_product(self) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT p.name, COUNT(s.id) as sale_count \n                FROM products p \n                LEFT JOIN sales s ON p.id = s.product_id \n                GROUP BY p.id\n            '
            rows = conn.execute(query).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_sales_with_product_names(self, start_date: datetime, end_date: datetime) -> list:
        return []

