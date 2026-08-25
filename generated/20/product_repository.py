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
            cursor = conn.cursor()
            cursor.execute('SELECT s.id, s.product_id, s.quantity, s.sale_date, p.name, p.price FROM sales s JOIN products p ON s.product_id = p.id WHERE s.product_id = ?', (product_id,))
            rows = cursor.fetchall()
            return [dict(id=row[0], product_id=row[1], quantity=row[2], sale_date=row[3], name=row[4], price=row[5]) for row in rows]

    def get_total_sales_amount(self) -> float:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(s.quantity * p.price) FROM sales s JOIN products p ON s.product_id = p.id')
            result = cursor.fetchone()
            total = result[0] if result[0] is not None else 0.0
            return float(total)

    def get_sales_count_per_product(self) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT p.id, p.name, COUNT(s.id) as sale_count FROM products p LEFT JOIN sales s ON p.id = s.product_id GROUP BY p.id, p.name')
            rows = cursor.fetchall()
            return {row[1]: row[2] for row in rows}

    def get_sales_with_product_names(self, start_date: str, end_date: str) -> list:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT s.id, s.product_id, s.quantity, s.sale_date, p.name, p.price \n                FROM sales s \n                JOIN products p ON s.product_id = p.id \n                WHERE s.sale_date BETWEEN ? AND ?\n            ', (start_date, end_date))
            rows = cursor.fetchall()
            return [dict(id=row[0], product_id=row[1], quantity=row[2], sale_date=row[3], name=row[4], price=row[5]) for row in rows]

