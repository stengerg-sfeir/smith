"""ProductRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import ProductNotFoundError
from models import Product


class ProductRepository:
    """SQLite repository for Product over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, product: Product) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO products (name, price, created_at) VALUES (?, ?, ?)",
                (product.name, product.price, product.created_at),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None, max_price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if start_date is not None:
                query += ' AND created_at >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND created_at <= ?'
                params.append(end_date)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'price', 'created_at']
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
                raise ProductNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM products WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_product_by_name(self, product_name: str) -> Optional[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE name = ?', (product_name,)).fetchall()
            return [Product(**dict(r)) for r in rows] if rows else None

    def get_products_by_price_range(self, min_price: float, max_price: float) -> list[Product]:
        return self.list(
            price=min_price,
            max_price=max_price,
        )

    def get_product_usage_count(self, product_name: str) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE name = ?', (product_name,)).fetchall()
            product = rows[0] if rows else None
            return product['id'] if product else 0

    def get_top_products_by_total_quantity_sold(self) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT p.id, p.name, p.price \n                FROM products p\n                JOIN orderitems oi ON p.id = oi.product_id\n                GROUP BY p.id, p.name, p.price\n                ORDER BY SUM(oi.quantity) DESC\n                LIMIT 10\n            ').fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_products_with_low_stock_alert(self, threshold: int) -> list[Product]:
        return []

    def get_product_sales_summary_by_date_range(self, start_date: datetime, end_date: datetime) -> dict[str, float]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_product_with_highest_average_order_price(self) -> Optional[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT p.id, p.name, p.price \n                FROM products p\n                JOIN orderitems oi ON p.id = oi.product_id\n                JOIN orders o ON oi.order_id = o.id\n                GROUP BY p.id, p.name, p.price\n                ORDER BY AVG(oi.unit_price) DESC\n                LIMIT 1\n            ').fetchall()
            return [Product(**dict(r)) for r in rows] if rows else None

