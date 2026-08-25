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

    def list(self, name: Optional[Any] = None, category: Optional[Any] = None, max_price: Optional[Any] = None, min_quantity: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if category is not None:
                query += ' AND category = ?'
                params.append(category)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            if min_quantity is not None:
                query += ' AND quantity >= ?'
                params.append(min_quantity)
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

    def search_products_by_name(self, name: str) -> list[Product]:
        return self.list(
            name=name,
        )

    def filter_products_by_category(self, category: str) -> list[Product]:
        return self.list(
            category=category,
        )

    def filter_products_by_max_price(self, max_price: float) -> list[Product]:
        return self.list(
            max_price=max_price,
        )

    def filter_products_by_min_quantity(self, min_quantity: int) -> list[Product]:
        return self.list(
            min_quantity=min_quantity,
        )

    def get_product_count(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM products')
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_product_report_by_category(self) -> dict[str, dict]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT category, COUNT(*) as count FROM products GROUP BY category')
            rows = cursor.fetchall()
            return {row[0]: {'count': row[1]} for row in rows}

    def get_product_summary(self) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT \n                    category, \n                    SUM(price * quantity) as total_value, \n                    SUM(quantity) as total_quantity \n                FROM products \n                GROUP BY category\n            ')
            rows = cursor.fetchall()
            return {row[0]: {'total_value': row[1], 'total_quantity': row[2]} for row in rows}

