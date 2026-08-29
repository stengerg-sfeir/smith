"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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
                "INSERT INTO orders (user_id, status, total_amount, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (order.user_id, order.status, order.total_amount, order.created_at, order.updated_at),
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

    def list(self, user_id: Optional[Any] = None, status: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['user_id', 'status', 'total_amount', 'created_at', 'updated_at']
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

    def get_orders_by_user_and_status(self, user_id: int, status: str) -> list[Order]:
        return self.list(
            user_id=user_id,
            status=status,
        )

    def get_orders_by_date_range_and_status(self, start_date: datetime, end_date: datetime, status: str) -> list[Order]:
        return []

    def get_total_orders_by_user_and_status(self, user_id: int, status: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(total_amount), 0) AS v FROM orders WHERE user_id = ? AND status = ?",
                (user_id, status)
            ).fetchone()
            return int(row["v"])

    def get_order_summary_by_status(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status AS k, SUM(total_amount) AS v FROM orders GROUP BY status"
            ).fetchall()
            return {r["k"]: float(r["v"] or 0) for r in rows}

    def get_orders_with_user_and_product_details(self, user_id: int) -> list[dict]:
        return self.list(
            user_id=user_id,
        )

    def get_orders_with_status_and_price_range(self, min_total: float, max_total: float, status: str) -> list[Order]:
        with self.db.connect() as conn:
            query = '\n                SELECT * FROM orders \n                WHERE total_amount BETWEEN ? AND ? \n                AND status = ?\n            '
            rows = conn.execute(query, (min_total, max_total, status)).fetchall()
            return [Order(**dict(r)) for r in rows]

