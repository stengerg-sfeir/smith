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
                "INSERT INTO products (name, description, price, quantity) VALUES (?, ?, ?, ?)",
                (product.name, product.description, product.price, product.quantity),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, price_max: Optional[Any] = None, quantity: Optional[Any] = None, quantity_max: Optional[Any] = None, description: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if price_max is not None:
                query += ' AND price <= ?'
                params.append(price_max)
            if quantity is not None:
                query += ' AND quantity >= ?'
                params.append(quantity)
            if quantity_max is not None:
                query += ' AND quantity <= ?'
                params.append(quantity_max)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'price', 'quantity']
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

    def get_product_by_name(self, name: str) -> Optional[Product]:
        return self.list(
            name=name,
        )

    def get_products_by_price_range(self, min_price: float, max_price: float) -> list[Product]:
        raise NotImplementedError()

    def get_products_with_low_stock(self) -> list[Product]:
        raise NotImplementedError()

    def get_product_count(self) -> int:
        raise NotImplementedError()

    def get_total_value_of_inventory(self) -> float:
        raise NotImplementedError()

    def search_products(self, query: str) -> list[Product]:
        raise NotImplementedError()

    def get_products_by_category(self, category: str) -> list[Product]:
        raise NotImplementedError('Category column does not exist in products table; this method cannot be implemented with the given schema.')

    def get_product_with_highest_price(self) -> Optional[Product]:
        raise NotImplementedError()

    def get_product_with_lowest_price(self) -> Optional[Product]:
        raise NotImplementedError()

