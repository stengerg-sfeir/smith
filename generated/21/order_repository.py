"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import OrderNotFoundError
from models import Order


class OrderRepository:
    """SQLite repository for Order over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order: Order) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (customer_id, order_date, status) VALUES (?, ?, ?)",
                (order.customer_id, order.order_date, order.status),
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

    def list(self, customer_id: Optional[Any] = None, order_date: Optional[Any] = None, order_date_end: Optional[Any] = None, status: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if order_date is not None:
                query += ' AND order_date >= ?'
                params.append(order_date)
            if order_date_end is not None:
                query += ' AND order_date <= ?'
                params.append(order_date_end)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_by_customer_and_order_date(self, customer_id: Any, order_date: Any) -> Optional[Order]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE customer_id = ? AND order_date = ?", (customer_id, order_date)
            ).fetchone()
            return Order(**dict(row)) if row else None

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'order_date', 'status']
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
                raise OrderNotFoundError(id)
            return True

    def delete(self, customer_id: Any, order_date: Any) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM orders WHERE customer_id = ? AND order_date = ?", (customer_id, order_date)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_orders_by_status_and_date_range(self, status: str, start_date: datetime, end_date: datetime) -> list[Order]:
        return []

    def get_orders_with_pending_status(self) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE status = ?', ('pending',)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_orders_by_customer_and_status(self, customer_id: int, status: str) -> list[Order]:
        return self.list(
            customer_id=customer_id,
            status=status,
        )

    def get_order_count_by_status(self, customer_id: int) -> dict[str, int]:
        return self.list(
            customer_id=customer_id,
        )

    def get_orders_with_date_filter_and_status(self, start_date: datetime, end_date: datetime, status: str) -> list[Order]:
        return []

    def get_recent_orders(self, days_ago: int) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE order_date >= datetime('now', '-' || ? || ' days')",
                (days_ago,)
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_orders_by_status_and_customer_name(self, customer_name: str, status: str) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM orders r JOIN customers o ON r.customer_id = o.id WHERE o.name = ?",
                (customer_name,)
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

