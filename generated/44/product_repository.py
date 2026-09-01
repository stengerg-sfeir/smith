"""ProductRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import ProductNotFoundError
from models import Product, Sale


class ProductRepository:
    """SQLite repository for Product over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, product: Product) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO products (name, price, stock_quantity, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (product.name, product.price, product.stock_quantity, product.created_at, product.updated_at),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, stock_quantity: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
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
        allowed = ['name', 'price', 'stock_quantity', 'created_at', 'updated_at']
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

    def get_product_by_name(self, name: str) -> Optional[Product]:
        return self.list(
            name=name,
        )

    def get_product_by_id(self, product_id: int) -> Optional[Product]:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
            if row is None:
                return None
            return Product(**dict(row))

    def get_products_by_category(self, category: str) -> list[Product]:
        return []

    def get_products_with_low_stock(self) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE stock_quantity <= 10').fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_sales_for_product(self, product_id: int, start_date: str, end_date: str) -> list[Sale]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM sales WHERE product_id = ? AND sale_date BETWEEN ? AND ?', (product_id, start_date, end_date)).fetchall()
            return [Sale(**dict(r)) for r in rows]

    def get_total_sales_by_product(self) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT products.name, SUM(sales.total_price) AS total_sales\n                   FROM sales\n                   JOIN products ON sales.product_id = products.id\n                   GROUP BY products.id').fetchall()
            result: Dict[str, float] = {}
            for row in rows:
                result[row[0]] = float(row[1]) if row[1] else 0.0
            return result

    def get_total_stock_value(self) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(price), 0) AS v FROM products",
            ).fetchone()
            return float(row["v"])

    def get_top_selling_products(self, limit: int) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM products LIMIT ?",
                (limit,)
            ).fetchall()
            return [Product(**dict(r)) for r in rows]

