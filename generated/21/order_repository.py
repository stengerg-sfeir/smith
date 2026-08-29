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

    def list(self, customer_id: Optional[Any] = None, order_date_from: Optional[Any] = None, order_date_to: Optional[Any] = None, order_date: Optional[Any] = None, status: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if order_date_from is not None:
                query += ' AND order_date >= ?'
                params.append(order_date_from)
            if order_date_to is not None:
                query += ' AND order_date <= ?'
                params.append(order_date_to)
            if order_date is not None:
                query += ' AND order_date = ?'
                params.append(order_date)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

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

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM orders WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_orders_by_status_and_date_range(self, status: str, start_date: datetime, end_date: datetime) -> list[Order]:
        return []

    def get_orders_with_customer_name_filter(self, customer_name: str) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM orders r JOIN customers o ON r.customer_id = o.id WHERE o.name = ?",
                (customer_name,)
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_order_count_by_status_and_date_range(self, status: str, start_date: str, end_date: str) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.execute('SELECT COUNT(*) AS count FROM orders WHERE status = ? AND order_date BETWEEN ? AND ?', (status, start_date, end_date))
            row = cursor.fetchone()
            return {'count': row[0] if row else 0}

    def get_orders_with_pagination_and_status_filter(self, status: str, page: int, page_size: int) -> dict[str, any]:
        with self.db.connect() as conn:
            offset = (page - 1) * page_size
            cursor = conn.execute('SELECT * FROM orders WHERE status = ? ORDER BY order_date DESC LIMIT ? OFFSET ?', (status, page_size, offset))
            rows = cursor.fetchall()
            return {'orders': [Order(**dict(r)) for r in rows], 'page': page, 'page_size': page_size, 'total': self.get_order_count_by_status_and_date_range(status, '1970-01-01', '2100-12-31')['count']}

    def get_orders_with_revenue_and_status_summary(self, status: str) -> dict[str, any]:
        return self.list(
            status=status,
        )

    def get_active_orders_count_by_customer_id(self, customer_id: int) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) AS count FROM orders WHERE customer_id = ? AND status = 'active'", (customer_id,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_orders_with_status_trend_over_time(self, start_date: str, end_date: str) -> dict[str, list[dict]]:
        with self.db.connect() as conn:
            cursor = conn.execute('\n                SELECT \n                    substr(order_date, 1, 7) AS month,\n                    status,\n                    COUNT(*) AS count\n                FROM orders \n                WHERE order_date BETWEEN ? AND ?\n                GROUP BY substr(order_date, 1, 7), status\n                ORDER BY substr(order_date, 1, 7)\n                ', (start_date, end_date))
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                month = row[0]
                status = row[1]
                count = row[2]
                if status not in result:
                    result[status] = []
                result[status].append({'month': month, 'count': count})
            return result

