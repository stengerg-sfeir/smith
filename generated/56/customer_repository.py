"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CustomerNotFoundError
from models import Customer


class CustomerRepository:
    """SQLite repository for Customer over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, customer: Customer) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO customers (name, email) VALUES (?, ?)",
                (customer.name, customer.email),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Customer]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ?", (id,)
            ).fetchone()
            return Customer(**dict(row)) if row else None

    def get_all(self) -> List[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM customers ORDER BY id"
            ).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def list(self, email: Optional[Any] = None, name: Optional[Any] = None, max_price: Optional[Any] = None, min_price: Optional[Any] = None) -> List[Customer]:
        with self.db.connect() as conn:
            query = "SELECT * FROM customers WHERE 1=1"
            params: List[Any] = []
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if max_price is not None:
                query += ' AND id <= ?'
                params.append(max_price)
            if min_price is not None:
                query += ' AND id >= ?'
                params.append(min_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE customers SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise CustomerNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM customers WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_customer_orders_with_products(self, customer_id: int, status_filter: str, product_name_filter: str) -> list[dict]:
        query = '\n        SELECT \n            o.id AS order_id,\n            o.created_at,\n            o.status,\n            p.id AS product_id,\n            p.name AS product_name,\n            p.price,\n            op.quantity\n        FROM orders o\n        JOIN order_products op ON o.id = op.order_id\n        JOIN products p ON op.product_id = p.id\n        WHERE o.customer_id = ?\n        AND o.status = ?\n        AND p.name LIKE ?\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (customer_id, status_filter, f'%{product_name_filter}%')).fetchall()
            return [dict(row) for row in rows]

    def get_customer_order_count_by_status(self, customer_id: int) -> dict:
        query = '\n        SELECT \n            o.status,\n            COUNT(*) AS count\n        FROM orders o\n        WHERE o.customer_id = ?\n        GROUP BY o.status\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (customer_id,)).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_product_stock_summary_by_customer(self, customer_id: int) -> dict:
        query = '\n        SELECT \n            p.id AS product_id,\n            p.name AS product_name,\n            p.stock_quantity,\n            SUM(op.quantity) AS total_quantity_purchased\n        FROM products p\n        JOIN order_products op ON p.id = op.product_id\n        JOIN orders o ON op.order_id = o.id\n        WHERE o.customer_id = ?\n        GROUP BY p.id, p.name, p.stock_quantity\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (customer_id,)).fetchall()
            return {row['product_id']: {'product_name': row['product_name'], 'stock_quantity': row['stock_quantity'], 'total_quantity_purchased': row['total_quantity_purchased']} for row in rows}

    def search_products_by_name_and_category(self, query: str, min_price: float, max_price: float) -> list[dict]:
        query_str = f'%{query}%'
        query = '\n        SELECT \n            id,\n            name,\n            price,\n            description\n        FROM products\n        WHERE name LIKE ?\n        AND price >= ?\n        AND price <= ?\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (query_str, min_price, max_price)).fetchall()
            return [dict(row) for row in rows]

    def get_active_orders_with_stock_impact(self) -> list[dict]:
        query = "\n        SELECT \n            o.id AS order_id,\n            o.created_at,\n            o.status,\n            p.id AS product_id,\n            p.name AS product_name,\n            op.quantity,\n            p.stock_quantity\n        FROM orders o\n        JOIN order_products op ON o.id = op.order_id\n        JOIN products p ON op.product_id = p.id\n        WHERE o.status != 'cancelled'\n        "
        with self.db.connect() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def get_customer_total_spent(self, customer_id: int) -> float:
        query = '\n        SELECT \n            SUM(o.total_amount) AS total_spent\n        FROM orders o\n        WHERE o.customer_id = ?\n        '
        with self.db.connect() as conn:
            row = conn.execute(query, (customer_id,)).fetchone()
            return row[0] if row[0] is not None else 0.0

    def get_product_sales_trend(self, product_id: int, start_date: str, end_date: str) -> list[dict]:
        query = '\n        SELECT \n            substr(o.created_at, 1, 7) AS month,\n            SUM(op.quantity) AS total_quantity_sold\n        FROM orders o\n        JOIN order_products op ON o.id = op.order_id\n        JOIN products p ON op.product_id = p.id\n        WHERE p.id = ?\n        AND o.created_at BETWEEN ? AND ?\n        GROUP BY substr(o.created_at, 1, 7)\n        ORDER BY month\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (product_id, start_date, end_date)).fetchall()
            return [dict(row) for row in rows]

