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

    def list(self, customer_id: Optional[Any] = None, status: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
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

    def get_order_by_customer_and_date_range(self, customer_id: int, start_date: str, end_date: str) -> Optional[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE customer_id = ? AND created_at BETWEEN ? AND ?', (customer_id, start_date, end_date)).fetchall()
            return [Order(**dict(r)) for r in rows] if rows else None

    def get_orders_with_status_and_total(self, status: str, min_total: float) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE status = ? AND total_amount >= ?', (status, min_total)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_order_count_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status AS k, COUNT(*) AS n FROM orders GROUP BY status"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_orders_for_report_period(self, start_date: datetime, end_date: datetime, include_cancelled: bool) -> list[Order]:
        return []

    def get_orders_with_customer_name(self, customer_name: str) -> list[Order]:
        return []

    def get_total_orders_in_period(self, start_date: str, end_date: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM orders WHERE created_at BETWEEN ? AND ?', (start_date, end_date)).fetchone()
            return row[0] if row else 0

