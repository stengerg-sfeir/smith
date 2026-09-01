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

    def list(self, customer_id: Optional[Any] = None, status: Optional[Any] = None, total_amount: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if total_amount is not None:
                query += ' AND total_amount = ?'
                params.append(total_amount)
            if start_date is not None:
                query += ' AND order_date >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND order_date <= ?'
                params.append(end_date)
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
            row = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
            if row is None:
                return None
            return Order(**dict(row))

    def get_order_by_customer_id(self, customer_id: int) -> list[Order]:
        return self.list(
            customer_id=customer_id,
        )

    def get_orders_by_status(self, status: str) -> list[Order]:
        return self.list(
            status=status,
        )

    def get_orders_in_date_range(self, start_date: datetime, end_date: datetime) -> list[Order]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_orders_with_customer_details(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT o.id, o.order_date, o.status, o.total_amount, o.created_at, o.updated_at,\n                c.name AS customer_name, c.email AS customer_email, c.phone AS customer_phone\n                FROM orders o\n                JOIN customers c ON o.customer_id = c.id\n            ').fetchall()
            return [dict(row) for row in rows]

    def get_orders_with_total_spent_by_customer(self) -> dict[int, float]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT o.name AS k, SUM(e.total_amount) AS v FROM orders e JOIN customers o ON e.customer_id = o.id GROUP BY o.name",
            ).fetchall()
            return {r["k"]: float(r["v"] or 0) for r in rows}

    def get_pending_orders_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM orders",
            ).fetchone()
            return int(row["n"])

    def get_orders_summary_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status AS k, SUM(total_amount) AS v FROM orders GROUP BY status"
            ).fetchall()
            return {r["k"]: float(r["v"] or 0) for r in rows}

    def get_orders_with_payment_method(self, payment_method: str) -> list[Order]:
        return []

    def get_orders_with_shipping_status(self, shipping_status: str) -> list[Order]:
        return []

