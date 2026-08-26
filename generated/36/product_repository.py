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
                "INSERT INTO products (name, description, price, category_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (product.name, product.description, product.price, product.category_id, product.created_at, product.updated_at),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, category_id: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'price', 'category_id', 'created_at', 'updated_at']
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

    def get_products_by_category_name(self, category_name: str) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE category_id = (SELECT id FROM categories WHERE name = ?)', (category_name,)).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_count_by_category(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT c.name, COUNT(p.id) AS count\n                FROM categories c\n                LEFT JOIN products p ON c.id = p.category_id\n                GROUP BY c.name\n            ').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_products_in_price_range(self, min_price: float, max_price: float) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE price BETWEEN ? AND ?', (min_price, max_price)).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_products_with_category_details(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT p.id, p.name, p.description, p.price, c.name AS category_name\n                FROM products p\n                JOIN categories c ON p.category_id = c.id\n            ').fetchall()
            return [dict(row) for row in rows]

    def get_category_product_summary(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT c.name, COUNT(p.id) AS product_count, AVG(p.price) AS avg_price\n                FROM categories c\n                LEFT JOIN products p ON c.id = p.category_id\n                GROUP BY c.name\n            ').fetchall()
            return {row[0]: {'product_count': row[1], 'avg_price': row[2]} for row in rows}

    def search_products_by_name(self, query: str) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE name LIKE ?', (f'%{query}%',)).fetchall()
            return [Product(**dict(r)) for r in rows]

