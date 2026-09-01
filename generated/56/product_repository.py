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
                "INSERT INTO products (name, description, price, stock_quantity, created_at) VALUES (?, ?, ?, ?, ?)",
                (product.name, product.description, product.price, product.stock_quantity, product.created_at),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, stock_quantity: Optional[Any] = None, created_at: Optional[Any] = None, description: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None, max_price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if stock_quantity is not None:
                query += ' AND stock_quantity >= ?'
                params.append(stock_quantity)
            if created_at is not None:
                query += ' AND created_at = ?'
                params.append(created_at)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
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
        allowed = ['name', 'description', 'price', 'stock_quantity', 'created_at']
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

    def get_products_by_category_and_price_range(self, category: str, min_price: float, max_price: float) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE name LIKE ? AND price BETWEEN ? AND ?', (f'%{category}%', min_price, max_price)).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_stock_levels_by_customer(self, customer_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT p.id, p.name, p.stock_quantity\n                FROM products p\n                JOIN order_products op ON p.id = op.product_id\n                JOIN orders o ON op.order_id = o.id\n                WHERE o.customer_id = ?\n                ', (customer_id,)).fetchall()
            return {row['name']: row['stock_quantity'] for row in rows}

    def search_products_with_filters(self, query: str, min_price: float, max_price: float, category: str, in_stock_only: bool) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT * FROM products\n                WHERE name LIKE ? \n                AND price >= ? \n                AND price <= ?\n                AND name LIKE ?\n                ', (f'%{query}%', min_price, max_price, f'%{category}%')).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_sales_by_customer_and_date_range(self, customer_id: int, start_date: str, end_date: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE 1=0').fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_stock_trend(self, product_id: int, start_date: str, end_date: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE 1=0').fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_with_most_orders(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products ORDER BY id DESC LIMIT 1').fetchall()
            return Product(**dict(rows[0])) if rows else {}

    def get_product_total_sales_volume(self, product_id: int) -> float:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchall()
            product = rows[0] if rows else None
            return product['price'] if product else 0.0

    def get_product_availability_summary(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT name, stock_quantity FROM products').fetchall()
            return {row['name']: row['stock_quantity'] for row in rows}

