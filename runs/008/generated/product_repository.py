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
                "INSERT INTO products (name, category, price, quantity) VALUES (?, ?, ?, ?)",
                (product.name, product.category, product.price, product.quantity),
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

    def list(self, category: Optional[Any] = None, threshold: Optional[Any] = None, name: Optional[Any] = None, price: Optional[Any] = None, quantity: Optional[Any] = None, max_price: Optional[Any] = None, min_price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if category is not None:
                query += ' AND category = ?'
                params.append(category)
            if threshold is not None:
                query += ' AND quantity <= ?'
                params.append(threshold)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price = ?'
                params.append(price)
            if quantity is not None:
                query += ' AND quantity = ?'
                params.append(quantity)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            if min_price is not None:
                query += ' AND price >= ?'
                params.append(min_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'category', 'price', 'quantity']
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

    def get_products_by_category_and_threshold(self, category: str, threshold: int) -> list[Product]:
        return self.list(
            category=category,
            threshold=threshold,
        )

    def get_product_count_by_category(self, category: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) AS v FROM products WHERE category = ?",
                (category,)
            ).fetchone()
            return int(row["v"])

    def get_low_stock_products(self) -> list[Product]:
        with self.db.connect() as conn:
            cursor = conn.execute('SELECT * FROM products WHERE quantity <= 10')
            rows = cursor.fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_products_with_price_range(self, min_price: float, max_price: float) -> list[Product]:
        return self.list(
            min_price=min_price,
            max_price=max_price,
        )

