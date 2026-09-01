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
                "INSERT INTO products (sku, name, category, price, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (product.sku, product.name, product.category, product.price, product.created_at, product.updated_at),
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

    def list(self, sku: Optional[Any] = None, category: Optional[Any] = None, price: Optional[Any] = None, name: Optional[Any] = None, max_price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if sku is not None:
                query += ' AND sku = ?'
                params.append(sku)
            if category is not None:
                query += ' AND category = ?'
                params.append(category)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_by_sku_and_category(self, sku: Any, category: Any) -> Optional[Product]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE sku = ? AND category = ?", (sku, category)
            ).fetchone()
            return Product(**dict(row)) if row else None

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['sku', 'name', 'category', 'price', 'created_at', 'updated_at']
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

    def delete(self, sku: Any, category: Any) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM products WHERE sku = ? AND category = ?", (sku, category)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_products_by_category(self, category: str) -> list[Product]:
        return self.list(
            category=category,
        )

    def get_products_by_sku_and_category(self, sku: str, category: str) -> list[Product]:
        return self.list(
            sku=sku,
            category=category,
        )

    def get_product_count_by_category(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT category AS k, COUNT(*) AS n FROM products GROUP BY category"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_products_with_price_range(self, min_price: float, max_price: float) -> list[Product]:
        return self.list(
            price=min_price,
            max_price=max_price,
        )

    def get_products_with_name_contains(self, search_term: str) -> list[Product]:
        return []

    def get_total_products_in_category(self, category: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(price), 0) AS v FROM products WHERE category = ?",
                (category,)
            ).fetchone()
            return int(row["v"])

    def get_products_with_category_and_sku_constraint(self, category: str, sku: str) -> list[Product]:
        return self.list(
            category=category,
            sku=sku,
        )

    def get_product_by_sku_and_category(self, sku: str, category: str) -> Optional[Product]:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM products WHERE sku = ? AND category = ?', (sku, category)).fetchone()
            if row is None:
                return None
            return Product(**dict(row))

    def generate_category_sales_report(self) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT category, SUM(price) AS total_price FROM products GROUP BY category').fetchall()
            report: dict[str, float] = {}
            for row in rows:
                report[row[0]] = row[1] if row[1] is not None else 0.0
            return report

    def get_products_with_updated_in_range(self, start_date: datetime, end_date: datetime) -> list[Product]:
        return []

