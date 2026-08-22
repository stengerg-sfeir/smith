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
                "INSERT INTO products (sku, name, category_id, price_cents, stock_qty, low_active) VALUES (?, ?, ?, ?, ?, ?)",
                (product.sku, product.name, product.category_id, product.price_cents, product.stock_qty, product.low_active),
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

    def list(self, category_id: Optional[Any] = None, low_only: Optional[Any] = None, name: Optional[Any] = None, price_cents: Optional[Any] = None, sku: Optional[Any] = None, stock_qty: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            if low_only is not None:
                query += ' AND low_active = ?'
                params.append(low_only)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price_cents is not None:
                query += ' AND price_cents = ?'
                params.append(price_cents)
            if sku is not None:
                query += ' AND sku = ?'
                params.append(sku)
            if stock_qty is not None:
                query += ' AND stock_qty = ?'
                params.append(stock_qty)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['sku', 'name', 'category_id', 'price_cents', 'stock_qty', 'low_active']
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

    def find_products_by_category(self, category_id: int) -> list[Product]:
        return self.list(
            category_id=category_id,
        )

    def find_low_stock_products(self, category_id: int) -> list[Product]:
        return self.list(
            category_id=category_id,
            low_only=True
        )

    def aggregate_stock_value_by_category(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    category_id,
                    SUM(stock_qty * price_cents) AS total_stock_value
                FROM products
                GROUP BY category_id
                """
            )
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                category_id = row[0]
                total_value = row[1]
                result[str(category_id)] = total_value
            return result

