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
                "INSERT INTO orders (customer_id, status, created_at, updated_at, total_amount) VALUES (?, ?, ?, ?, ?)",
                (order.customer_id, order.status, order.created_at, order.updated_at, order.total_amount),
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

    def list(self, status: Optional[Any] = None, created_at: Optional[Any] = None, customer_id: Optional[Any] = None, total_amount: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if total_amount is not None:
                query += ' AND total_amount = ?'
                params.append(total_amount)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'status', 'created_at', 'updated_at', 'total_amount']
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

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM orders WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_order_by_customer_and_status(self, customer_id: int, status: str) -> Optional[Order]:
        return self.list(
            customer_id=customer_id,
            status=status,
        )

    def get_orders_by_status_and_date_range(self, status: str, start_date: datetime, end_date: datetime) -> list[Order]:
        return self.list(
            status=status,
        )

    def get_total_orders_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT status, COUNT(*) AS count FROM orders GROUP BY status')
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    def get_orders_with_customer_count(self) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT o.id, o.customer_id, o.status, o.total_amount, o.created_at, o.updated_at,\n                (SELECT COUNT(*) FROM orders o2 WHERE o2.customer_id = o.customer_id) AS customer_order_count\n                FROM orders o\n                GROUP BY o.customer_id, o.id, o.status, o.total_amount, o.created_at, o.updated_at\n            ')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_pending_orders_count(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_confirmed_orders_count(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'confirmed'")
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_shipped_orders_count(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'shipped'")
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_cancelled_orders_count(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'cancelled'")
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_orders_with_latest_status_change(self) -> list[Order]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT o.id, o.customer_id, o.status, o.total_amount, o.created_at, o.updated_at\n                FROM orders o\n                ORDER BY o.updated_at DESC\n                LIMIT 10\n            ')
            rows = cursor.fetchall()
            return [Order(**dict(row)) for row in rows]

    def get_orders_with_total_amount_range(self, min_amount: float, max_amount: float) -> list[Order]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT id, customer_id, status, total_amount, created_at, updated_at\n                FROM orders\n                WHERE total_amount BETWEEN ? AND ?\n            ', (min_amount, max_amount))
            rows = cursor.fetchall()
            return [Order(**dict(row)) for row in rows]

