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
                "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
                (product.name, product.description, product.price),
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

    def list(self, name: Optional[Any] = None, price: Optional[Any] = None, max_price: Optional[Any] = None) -> List[Product]:
        with self.db.connect() as conn:
            query = "SELECT * FROM products WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if price is not None:
                query += ' AND price >= ?'
                params.append(price)
            if max_price is not None:
                query += ' AND price <= ?'
                params.append(max_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Product(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'price']
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

    def get_products_by_name_like(self, name_like: str) -> List[Product]:
        return []

    def get_products_by_price_range(self, min_price: float, max_price: float) -> List[Product]:
        return self.list(
            price=min_price,
            max_price=max_price,
        )

    def get_product_with_sales_summary(self, product_id: int, date_range_start: str, date_range_end: str) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    p.id,\n                    p.name,\n                    p.description,\n                    p.price,\n                    SUM(il.quantity) AS total_quantity_sold,\n                    SUM(il.quantity * il.unit_price) AS total_revenue\n                FROM products p\n                JOIN invoicelines il ON p.id = il.product_id\n                WHERE il.product_id = ?\n                    AND il.invoice_id IN (\n                        SELECT id FROM invoices \n                        WHERE created_at BETWEEN ? AND ?\n                    )\n                GROUP BY p.id, p.name, p.description, p.price\n            '
            rows = conn.execute(query, (product_id, date_range_start, date_range_end)).fetchall()
            if not rows:
                raise ProductNotFoundError(f'Product with id {product_id} not found or no sales in date range')
            row = rows[0]
            return {'id': row[0], 'name': row[1], 'description': row[2], 'price': row[3], 'total_quantity_sold': row[4], 'total_revenue': row[5]}

    def get_total_sales_by_product(self) -> dict:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    p.id,\n                    p.name,\n                    p.description,\n                    p.price,\n                    SUM(il.quantity) AS total_quantity_sold,\n                    SUM(il.quantity * il.unit_price) AS total_revenue\n                FROM products p\n                JOIN invoicelines il ON p.id = il.product_id\n                GROUP BY p.id, p.name, p.description, p.price\n            '
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]

    def get_top_selling_products_by_quantity(self, limit: int) -> list[tuple[str, int]]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    p.name,\n                    SUM(il.quantity) AS total_quantity\n                FROM products p\n                JOIN invoicelines il ON p.id = il.product_id\n                GROUP BY p.id, p.name\n                ORDER BY total_quantity DESC\n                LIMIT ?\n            '
            rows = conn.execute(query, (limit,)).fetchall()
            return [(row[0], row[1]) for row in rows]

    def get_products_with_customer_usage(self, customer_id: int, min_quantity: int) -> List[Product]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    p.id,\n                    p.name,\n                    p.description,\n                    p.price\n                FROM products p\n                JOIN invoicelines il ON p.id = il.product_id\n                JOIN invoices i ON il.invoice_id = i.id\n                JOIN customers c ON i.customer_id = c.id\n                WHERE c.id = ?\n                    AND il.quantity >= ?\n                GROUP BY p.id, p.name, p.description, p.price\n            '
            rows = conn.execute(query, (customer_id, min_quantity)).fetchall()
            return [Product(**dict(r)) for r in rows]

