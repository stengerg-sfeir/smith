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
                "INSERT INTO products (name, price, created_at) VALUES (?, ?, ?)",
                (product.name, product.price, product.created_at),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if start_date is not None:
                query += ' AND created_at >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND created_at <= ?'
                params.append(end_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'price', 'created_at']
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

    def get_product_by_name(self, product_name: str) -> Optional[Product]:
        raise NotImplementedError()

    def get_products_by_price_range(self, min_price: float, max_price: float) -> list[Product]:
        raise NotImplementedError()

    def get_product_usage_count(self, product_name: str) -> int:
        raise NotImplementedError()

    def get_top_products_by_total_quantity_sold(self) -> list[Product]:
        raise NotImplementedError()

    def get_products_with_low_stock_alert(self, threshold: int) -> list[Product]:
        raise NotImplementedError("The 'products' table does not have a 'quantity' column. This method cannot be implemented as per the designed schema.")

    def get_product_sales_summary_by_date_range(self, start_date: datetime, end_date: datetime) -> dict[str, float]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_product_with_highest_average_order_price(self) -> Optional[Product]:
        raise NotImplementedError()

