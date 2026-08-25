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
                "INSERT INTO products (sku, name, category, price, stock_quantity) VALUES (?, ?, ?, ?, ?)",
                (product.sku, product.name, product.category, product.price, product.stock_quantity),
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

    def list(self, sku: Optional[Any] = None, name: Optional[Any] = None, category: Optional[Any] = None, min_price: Optional[Any] = None, max_price: Optional[Any] = None, min_stock: Optional[Any] = None, max_stock: Optional[Any] = None, price: Optional[Any] = None, stock_quantity: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if sku is not None:
                query += ' AND sku = ?'
                params.append(sku)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if category is not None:
                query += ' AND category = ?'
                params.append(category)
            if min_price is not None:
                query += ' AND price >= ?'
                params.append(min_price)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            if min_stock is not None:
                query += ' AND stock_quantity >= ?'
                params.append(min_stock)
            if max_stock is not None:
                query += ' AND stock_quantity <= ?'
                params.append(max_stock)
            if price is not None:
                query += ' AND price = ?'
                params.append(price)
            if stock_quantity is not None:
                query += ' AND stock_quantity = ?'
                params.append(stock_quantity)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['sku', 'name', 'category', 'price', 'stock_quantity']
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

    def get_products_by_category(self, category: str) -> list[Product]:
        return self.list(
            category=category,
        )

    def get_products_low_stock(self) -> list[Product]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM products WHERE stock_quantity <= 10')
            rows = cursor.fetchall()
            return [Product(**dict(r)) for r in rows]

    def search_products(self, query: str, category: str) -> list[Product]:
        return self.list(
            category=category,
        )

    def get_product_count_by_category(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT category, COUNT(*) as count FROM products GROUP BY category')
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    def get_total_stock_value(self) -> float:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(stock_quantity * price) FROM products')
            row = cursor.fetchone()
            return row[0] if row[0] is not None else 0.0

    def get_products_with_price_range(self, min_price: float, max_price: float) -> list[Product]:
        return self.list(
            min_price=min_price,
            max_price=max_price,
        )

