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
                "INSERT INTO products (name, description, price, stock_quantity, category_id) VALUES (?, ?, ?, ?, ?)",
                (product.name, product.description, product.price, product.stock_quantity, product.category_id),
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

    def list(self, name: Optional[Any] = None, category_id: Optional[Any] = None, price: Optional[Any] = None, description: Optional[Any] = None, stock_quantity: Optional[Any] = None, max_price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if stock_quantity is not None:
                query += ' AND stock_quantity = ?'
                params.append(stock_quantity)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'price', 'stock_quantity', 'category_id']
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

    def get_products_by_category(self, category_id: int, status_filter: str, min_stock: int, max_price: float) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM products r JOIN categories o ON r.category_id = o.id WHERE o.id = ?",
                (category_id,)
            ).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_total_sales_by_category(self, category_id: int, date_from: str, date_to: str) -> float:
        with self.db.connect() as conn:
            query = '\n                SELECT SUM(oi.quantity * p.price) AS total_sales\n                FROM order_items oi\n                JOIN products p ON oi.product_id = p.id\n                JOIN orders o ON oi.order_id = o.id\n                WHERE p.category_id = ?\n                AND o.created_at BETWEEN ? AND ?\n            '
            rows = conn.execute(query, (category_id, date_from, date_to)).fetchone()
            return rows[0] if rows[0] is not None else 0.0

    def get_product_sales_trend(self, product_id: int, start_date: str, end_date: str, interval: str) -> list[dict]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    substr(o.created_at, 1, 7) AS month,\n                    SUM(oi.quantity * p.price) AS total_sales\n                FROM order_items oi\n                JOIN products p ON oi.product_id = p.id\n                JOIN orders o ON oi.order_id = o.id\n                WHERE p.id = ?\n                AND o.created_at BETWEEN ? AND ?\n                GROUP BY substr(o.created_at, 1, 7)\n                ORDER BY substr(o.created_at, 1, 7)\n            '
            rows = conn.execute(query, (product_id, start_date, end_date)).fetchall()
            return [{'month': row[0], 'total_sales': row[1] if row[1] is not None else 0} for row in rows]

    def get_low_stock_alerts(self) -> list[Product]:
        with self.db.connect() as conn:
            query = '\n                SELECT p.*\n                FROM products p\n                WHERE p.stock_quantity < 10\n            '
            rows = conn.execute(query).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_performance_summary(self, date_from: str, date_to: str) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    p.id,\n                    p.name,\n                    p.category_id,\n                    SUM(oi.quantity) AS total_quantity_sold,\n                    SUM(oi.quantity * p.price) AS total_revenue,\n                    AVG(p.price) AS average_price,\n                    p.stock_quantity\n                FROM products p\n                JOIN order_items oi ON p.id = oi.product_id\n                JOIN orders o ON oi.order_id = o.id\n                WHERE o.created_at BETWEEN ? AND ?\n                GROUP BY p.id, p.name, p.category_id, p.price, p.stock_quantity\n            '
            rows = conn.execute(query, (date_from, date_to)).fetchall()
            return {'total_products': len(rows), 'total_revenue': sum((row[4] for row in rows)), 'average_price': sum((row[5] for row in rows)) / len(rows) if rows else 0, 'low_stock_count': sum((1 for row in rows if row[5] < 10)), 'top_selling_product': max(((row[1], row[3]) for row in rows)) if rows else (None, 0)}

    def search_products_by_name_or_description(self, query: str, category_id: int, min_price: float, max_price: float) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM products r JOIN categories o ON r.category_id = o.id WHERE o.id = ?",
                (category_id,)
            ).fetchall()
            return [Product(**dict(r)) for r in rows]

