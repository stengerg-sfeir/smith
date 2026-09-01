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
                "INSERT INTO orders (customer_id, status, total_amount, created_at, cancelled_at) VALUES (?, ?, ?, ?, ?)",
                (order.customer_id, order.status, order.total_amount, order.created_at, order.cancelled_at),
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

    def list(self, status: Optional[Any] = None, total_amount: Optional[Any] = None, created_at: Optional[Any] = None, customer_id: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if total_amount is not None:
                query += ' AND total_amount >= ?'
                params.append(total_amount)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'status', 'total_amount', 'created_at', 'cancelled_at']
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

    def get_orders_by_customer_and_status(self, customer_id: int, status: str) -> list[dict]:
        return self.list(
            customer_id=customer_id,
            status=status,
        )

    def get_orders_with_product_details(self, order_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_active_orders_with_product_stock_impact(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE status = ? AND cancelled_at IS NULL', ('active',)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_order_count_by_status(self, customer_id: int) -> dict:
        return self.list(
            customer_id=customer_id,
        )

    def cancel_order(self, order_id: int) -> bool:
        with self.db.connect() as conn:
            result = conn.execute('UPDATE orders SET cancelled_at = ? WHERE id = ? AND cancelled_at IS NULL', (None, order_id)).rowcount
            return result > 0

    def get_orders_with_stock_changes(self, start_date: datetime, end_date: datetime) -> list[dict]:
        return []

    def get_orders_by_date_range_and_status(self, start_date: datetime, end_date: datetime, status: str) -> list[dict]:
        return []

    def get_total_order_value_by_customer(self, customer_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(total_amount), 0) AS v FROM orders WHERE customer_id = ?",
                (customer_id,)
            ).fetchone()
            return float(row["v"])

    def get_orders_with_product_name_filter(self, product_name: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM orders r JOIN order_products j ON r.id = j.order_id JOIN products o ON j.product_id = o.id WHERE o.name = ?",
                (product_name,)
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

