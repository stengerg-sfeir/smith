"""ProductRepository data access."""
from __future__ import annotations

from typing import Any, List, Optional

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
                "INSERT INTO products (name, description, price, stock_quantity, category) VALUES (?, ?, ?, ?, ?)",
                (product.name, product.description, product.price, product.stock_quantity, product.category),
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

    def list(self, name: Optional[Any] = None, category: Optional[Any] = None, price_min: Optional[Any] = None, price_max: Optional[Any] = None, stock_min: Optional[Any] = None, stock_max: Optional[Any] = None, description: Optional[Any] = None, price: Optional[Any] = None, stock_quantity: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if category is not None:
                query += ' AND category = ?'
                params.append(category)
            if price_min is not None:
                query += ' AND price >= ?'
                params.append(price_min)
            if price_max is not None:
                query += ' AND price <= ?'
                params.append(price_max)
            if stock_min is not None:
                query += ' AND stock_quantity >= ?'
                params.append(stock_min)
            if stock_max is not None:
                query += ' AND stock_quantity <= ?'
                params.append(stock_max)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if price is not None:
                query += ' AND price = ?'
                params.append(price)
            if stock_quantity is not None:
                query += ' AND stock_quantity = ?'
                params.append(stock_quantity)

            rows = conn.execute(query, params).fetchall()
            return [Product(**dict(r)) for r in rows]
