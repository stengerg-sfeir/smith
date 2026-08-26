"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import OrderNotFoundError
from models import Customer, Order


class OrderRepository:
    """SQLite repository for Order over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order: Order) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (customer_id, order_date, total_amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (order.customer_id, order.order_date, order.total_amount, order.status, order.created_at, order.updated_at),
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

    def list(self, customer_id: Optional[Any] = None, order_date: Optional[Any] = None, order_date_end: Optional[Any] = None, total_amount: Optional[Any] = None, total_amount_end: Optional[Any] = None, status: Optional[Any] = None) -> List[Order]:
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
            if total_amount is not None:
                query += ' AND total_amount >= ?'
                params.append(total_amount)
            if total_amount_end is not None:
                query += ' AND total_amount <= ?'
                params.append(total_amount_end)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'order_date', 'total_amount', 'status', 'created_at', 'updated_at']
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

    def get_order_by_id(self, order_id: int) -> Optional[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchall()
            if not rows:
                return None
            return Order(**dict(rows[0]))

    def get_orders_by_status(self, status: str, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> list[Order]:
        return self.list(
            status=status,
        )

    def get_orders_by_customer(self, customer_id: int, status: Optional[str] = None, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> list[Order]:
        return self.list(
            customer_id=customer_id,
            status=status,
        )

    def get_order_summary_by_status(self) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, SUM(total_amount) FROM orders GROUP BY status').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_total_orders_count(self) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM orders').fetchall()
            return rows[0][0]

    def get_orders_with_customer_details(self, order_id: int) -> dict[Order, Customer]:
        raise NotImplementedError()

    def get_orders_in_date_range(self, from_date: str, to_date: str) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE order_date BETWEEN ? AND ?', (from_date, to_date)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_orders_by_total_range(self, min_amount: float, max_amount: float) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE total_amount BETWEEN ? AND ?', (min_amount, max_amount)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_active_orders_count(self) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM orders WHERE status = ?', ('active',)).fetchall()
            return rows[0][0]

    def get_order_with_most_spent(self) -> Optional[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders ORDER BY total_amount DESC LIMIT 1').fetchall()
            if not rows:
                return None
            return Order(**dict(rows[0]))

