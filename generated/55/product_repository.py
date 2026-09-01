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
                "INSERT INTO products (name, description, price, stock_quantity, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (product.name, product.description, product.price, product.stock_quantity, product.created_at, product.updated_at),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, stock_quantity: Optional[Any] = None, description: Optional[Any] = None) -> List[Product]:
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
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'price', 'stock_quantity', 'created_at', 'updated_at']
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

    def get_product_with_stock_status(self, product_id: int) -> Optional[Product]:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
            return Product(**dict(row)) if row else None

    def list_products_with_stock_levels(self, min_stock: int, max_stock: int, name_filter: str) -> list[Product]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM products WHERE stock_quantity BETWEEN ? AND ? AND name LIKE ?'
            rows = conn.execute(query, (min_stock, max_stock, f'%{name_filter}%')).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_total_stock_quantity(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(stock_quantity), 0) AS v FROM products",
            ).fetchone()
            return int(row["v"])

    def get_product_sales_summary(self, product_id: int, start_date: str, end_date: str) -> dict[str, any]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    SUM(s.quantity) AS total_quantity_sold,\n                    SUM(s.quantity * s.sale_price) AS total_revenue\n                FROM sales s\n                JOIN products p ON s.product_id = p.id\n                WHERE p.id = ? \n                  AND s.sold_at BETWEEN ? AND ?\n            '
            row = conn.execute(query, (product_id, start_date, end_date)).fetchone()
            result = {}
            if row:
                result['total_quantity_sold'] = row[0] or 0
                result['total_revenue'] = row[1] or 0
            return result

    def get_low_stock_alerts(self) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM products WHERE stock_quantity <= 10').fetchall()
            return [dict(r) for r in rows]

    def get_product_by_name(self, name: str) -> Optional[Product]:
        return self.list(
            name=name,
        )


    def get_product_by_id(self, id: int) -> Optional[Product]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?", (id,)
            ).fetchone()
            return Product(**dict(row)) if row else None

