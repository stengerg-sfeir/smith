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
                "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
                (product.name, product.description, product.price),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, max_price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'price']
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

    def get_products_by_name_like(self, name: Optional[str] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += " AND name LIKE ?"
                params.append(f"%{name}%")
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]
