"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Order, OrderItem, Product


class OrderRepository:
    """SQLite repository for Order over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order: Order) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (customer_name, created_at, updated_at) VALUES (?, ?, ?)",
                (order.customer_name, order.created_at, order.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Order]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (id,)
            ).fetchone()
            return Order(**dict(row)) if row else None

    def get_all(self) -> List[Order]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY id"
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def list(self, customer_name: Optional[Any] = None, created_at: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_name is not None:
                query += ' AND customer_name = ?'
                params.append(customer_name)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_name', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE orders SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM orders WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_order_with_items_by_customer(self, customer_name: str) -> list[OrderWithItems]:
        return self.list(
            customer_name=customer_name,
        )

    def get_total_orders_by_customer(self, customer_name: str) -> int:
        return self.list(
            customer_name=customer_name,
        )

    def get_order_total_by_customer(self, customer_name: str) -> float:
        return self.list(
            customer_name=customer_name,
        )

    def get_product_usage_in_orders(self, product_name: str) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM orders r JOIN orderitems j ON r.id = j.order_id JOIN products o ON j.product_id = o.id WHERE o.name = ?",
                (product_name,)
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_orders_with_high_value_items(self, min_total_amount: float) -> list[Order]:
        query = '\n            SELECT o.id, o.customer_name, o.created_at, o.updated_at\n            FROM orders o\n            JOIN orderitems oi ON o.id = oi.order_id\n            GROUP BY o.id, o.customer_name, o.created_at, o.updated_at\n            HAVING SUM(oi.quantity * oi.unit_price) >= ?\n        '
        with self.db.connect() as conn:
            conn.execute(query, (min_total_amount,))
            rows = conn.execute(query, (min_total_amount,)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_order_items_by_product_name(self, product_name: str, min_quantity: int) -> list[OrderItem]:
        query = '\n            SELECT oi.id, oi.order_id, oi.product_id, oi.quantity, oi.unit_price\n            FROM orderitems oi\n            JOIN products p ON oi.product_id = p.id\n            WHERE p.name = ? AND oi.quantity >= ?\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (product_name, min_quantity)).fetchall()
            return [OrderItem(**dict(r)) for r in rows]

    def get_order_summary_by_date_range(self, start_date: str, end_date: str) -> dict[str, float]:
        query = '\n            SELECT \n                substr(o.created_at, 1, 7) AS month,\n                SUM(oi.quantity * oi.unit_price) AS total_revenue\n            FROM orders o\n            JOIN orderitems oi ON o.id = oi.order_id\n            WHERE o.created_at BETWEEN ? AND ?\n            GROUP BY substr(o.created_at, 1, 7)\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            result = {}
            for row in rows:
                month = row[0]
                revenue = row[1]
                result[month] = revenue
            return result

    def get_most_popular_product(self) -> Product:
        query = '\n            SELECT p.id, p.name, p.price\n            FROM products p\n            JOIN orderitems oi ON p.id = oi.product_id\n            GROUP BY p.id, p.name, p.price\n            ORDER BY SUM(oi.quantity) DESC\n            LIMIT 1\n        '
        with self.db.connect() as conn:
            row = conn.execute(query).fetchone()
            if row is None:
                return None
            return Product(**dict(row))

    def get_orders_with_missing_products(self) -> list[Order]:
        query = '\n            SELECT o.id, o.customer_name, o.created_at, o.updated_at\n            FROM orders o\n            JOIN orderitems oi ON o.id = oi.order_id\n            WHERE oi.product_id NOT IN (SELECT id FROM products)\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query).fetchall()
            return [Order(**dict(r)) for r in rows]

