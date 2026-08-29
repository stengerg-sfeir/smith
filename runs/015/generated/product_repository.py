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
                "INSERT INTO products (name, price, quantity, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (product.name, product.price, product.quantity, product.created_at, product.updated_at),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, price_gte: Optional[Any] = None, price_lte: Optional[Any] = None, quantity: Optional[Any] = None, quantity_gte: Optional[Any] = None, quantity_lte: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price = ?'
                params.append(price)
            if price_gte is not None:
                query += ' AND price >= ?'
                params.append(price_gte)
            if price_lte is not None:
                query += ' AND price <= ?'
                params.append(price_lte)
            if quantity is not None:
                query += ' AND quantity = ?'
                params.append(quantity)
            if quantity_gte is not None:
                query += ' AND quantity >= ?'
                params.append(quantity_gte)
            if quantity_lte is not None:
                query += ' AND quantity <= ?'
                params.append(quantity_lte)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'price', 'quantity', 'created_at', 'updated_at']
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

    def list_products_by_name(self, sort_order: str, filter_name: str) -> list[Product]:
        return []

    def list_products_by_price(self, sort_order: str, min_price: float, max_price: float) -> list[Product]:
        query = '\n        SELECT * FROM products \n        WHERE price BETWEEN ? AND ?\n        ORDER BY price \n        '
        if sort_order == 'asc':
            query += ' ASC'
        elif sort_order == 'desc':
            query += ' DESC'
        else:
            query += ' ASC'
        with self.db.connect() as conn:
            rows = conn.execute(query, (min_price, max_price)).fetchall()
            return [Product(**dict(r)) for r in rows]

    def list_products_by_quantity(self, sort_order: str, min_quantity: int, max_quantity: int) -> list[Product]:
        query = '\n        SELECT * FROM products \n        WHERE quantity BETWEEN ? AND ?\n        ORDER BY quantity \n        '
        if sort_order == 'asc':
            query += ' ASC'
        elif sort_order == 'desc':
            query += ' DESC'
        else:
            query += ' ASC'
        with self.db.connect() as conn:
            rows = conn.execute(query, (min_quantity, max_quantity)).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM products",
            ).fetchone()
            return int(row["n"])

    def get_product_report_by_category(self, category: str) -> dict:
        return {}

    def list_products_with_pagination(self, page: int, page_size: int, sort_field: str, sort_order: str) -> list[Product]:
        return []

