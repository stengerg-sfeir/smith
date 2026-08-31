"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Order, Product


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

    def list(self, customer_name: Optional[Any] = None, created_at_from: Optional[Any] = None, created_at_to: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_name is not None:
                query += ' AND customer_name = ?'
                params.append(customer_name)
            if created_at_from is not None:
                query += ' AND created_at >= ?'
                params.append(created_at_from)
            if created_at_to is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_to)
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

    def get_order_total_amount(self, order_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute('SELECT SUM(o.quantity * oi.unit_price) FROM orderitems oi JOIN orders o ON oi.order_id = o.id WHERE o.id = ?', (order_id,)).fetchone()
            return row[0] if row[0] is not None else 0.0

    def list_orders_by_customer(self, customer_name: str, start_date: datetime, end_date: datetime) -> list[Order]:
        return []

    def get_order_with_items(self, order_id: int) -> OrderWithItems:
        return None

    def get_total_revenue_by_product(self, start_date: str, end_date: str) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT p.name, SUM(oi.quantity * oi.unit_price) AS total_revenue\n                FROM orderitems oi\n                JOIN products p ON oi.product_id = p.id\n                JOIN orders o ON oi.order_id = o.id\n                WHERE o.created_at BETWEEN ? AND ?\n                GROUP BY p.name\n                ', (start_date, end_date)).fetchall()
            return {row[0]: row[1] for row in rows}

    def list_orders_with_product_summary(self, start_date: datetime, end_date: datetime) -> list[OrderWithProductSummary]:
        return []

    def get_most_popular_product(self) -> Product:
        with self.db.connect() as conn:
            row = conn.execute('\n                SELECT p.name, p.price, p.id\n                FROM orderitems oi\n                JOIN products p ON oi.product_id = p.id\n                GROUP BY p.id\n                ORDER BY SUM(oi.quantity) DESC\n                LIMIT 1\n                ').fetchone()
            if row is None:
                return None
            return Product(**dict(row))

    def get_orders_with_quantity_over_limit(self, min_quantity: int) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT o.id, o.customer_name, o.created_at, o.updated_at\n                FROM orders o\n                JOIN orderitems oi ON o.id = oi.order_id\n                WHERE oi.quantity > ?\n                ', (min_quantity,)).fetchall()
            return [Order(**dict(r)) for r in rows]

