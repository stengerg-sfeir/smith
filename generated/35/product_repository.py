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
                "INSERT INTO products (name, description, price, stock_quantity, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (product.name, product.description, product.price, product.stock_quantity, product.category, product.created_at, product.updated_at),
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
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'price', 'stock_quantity', 'category', 'created_at', 'updated_at']
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

    def bulk_update_stock(self, product_ids: list[int], new_stock_quantity: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute('UPDATE products SET stock_quantity = ? WHERE id IN (' + ','.join(('?' for _ in product_ids)) + ')', [*[new_stock_quantity] * len(product_ids), *product_ids])
            return cursor.rowcount > 0

    def get_products_by_category_and_price_range(self, category: Optional[str] = None, min_price: Optional[float] = None, max_price: Optional[float] = None) -> list[Product]:
        return self.list(
            category=category,
            price_min=min_price,
            price_max=max_price,
        )

    def get_total_stock_by_category(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT category, SUM(stock_quantity) AS total_stock FROM products GROUP BY category').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_products_with_low_stock_alert(self) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT id, name, category, description, price, stock_quantity, created_at, updated_at FROM products WHERE stock_quantity <= 10').fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_product_sales_trend(self, start_date: Optional[str]=None, end_date: Optional[str]=None) -> list[tuple[str, float]]:
        return []

