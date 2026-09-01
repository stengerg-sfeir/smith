"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, List, Optional

from database import Database
from models import Order


class OrderRepository:
    """SQLite repository for Order over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order: Order) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (customer_id, order_date, status, total_amount, discount_id, tax_rate) VALUES (?, ?, ?, ?, ?, ?)",
                (order.customer_id, order.order_date, order.status, order.total_amount, order.discount_id, order.tax_rate),
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

    def list(self, customer_id: Optional[Any] = None, order_date: Optional[Any] = None, status: Optional[Any] = None, total_amount: Optional[Any] = None, discount_id: Optional[Any] = None, tax_rate: Optional[Any] = None, max_rate: Optional[Any] = None, min_rate: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if order_date is not None:
                query += ' AND order_date >= ?'
                params.append(order_date)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if total_amount is not None:
                query += ' AND total_amount >= ?'
                params.append(total_amount)
            if discount_id is not None:
                query += ' AND discount_id = ?'
                params.append(discount_id)
            if tax_rate is not None:
                query += ' AND tax_rate = ?'
                params.append(tax_rate)
            if max_rate is not None:
                query += ' AND tax_rate <= ?'
                params.append(max_rate)
            if min_rate is not None:
                query += ' AND tax_rate >= ?'
                params.append(min_rate)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, order: Order) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE orders SET customer_id = ?, order_date = ?, status = ?, total_amount = ?, discount_id = ?, tax_rate = ? WHERE id = ?",
                (order.customer_id, order.order_date, order.status, order.total_amount, order.discount_id, order.tax_rate, order.id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM orders WHERE id = ?", (id,))
            conn.commit()
            return cur.rowcount > 0
