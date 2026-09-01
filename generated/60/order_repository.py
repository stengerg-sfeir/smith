"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import OrderNotFoundError
from models import Order, Product


class OrderRepository:
    """SQLite repository for Order over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order: Order) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (customer_id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (order.customer_id, order.status, order.created_at, order.updated_at),
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

    def list(self, customer_id: Optional[Any] = None, status: Optional[Any] = None, created_at: Optional[Any] = None) -> List[Order]:
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
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'status', 'created_at', 'updated_at']
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

    def get_order_items_by_order_id(self, order_id: int) -> list[Product]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,)).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_orders_by_customer_id(self, customer_id: int, status_filter: str, date_from: datetime, date_to: datetime) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM orders r JOIN customers o ON r.customer_id = o.id WHERE o.id = ?",
                (customer_id,)
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_orders_by_status_and_date_range(self, status: str, date_from: str, date_to: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE status = ? AND created_at BETWEEN ? AND ?', (status, date_from, date_to)).fetchall()
            return [dict(r) for r in rows]

    def get_order_count_by_status(self, date_from: str, date_to: str) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, COUNT(*) as count FROM orders WHERE created_at BETWEEN ? AND ? GROUP BY status', (date_from, date_to)).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_total_order_value_by_status(self, date_from: str, date_to: str) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT status, SUM(price * quantity) as total_value FROM orders o JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id WHERE o.created_at BETWEEN ? AND ? GROUP BY o.status', (date_from, date_to)).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_orders_with_product_sales_trend(self, order_id: int, start_date: str, end_date: str, interval: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders o JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id WHERE o.id = ? AND o.created_at BETWEEN ? AND ?', (order_id, start_date, end_date)).fetchall()
            return [dict(r) for r in rows]

    def get_order_summary_by_customer(self, customer_id: int, date_from: datetime, date_to: datetime) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM orders r JOIN customers o ON r.customer_id = o.id WHERE o.id = ?",
                (customer_id,)
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_orders_with_invoices(self, order_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders o JOIN invoices i ON o.id = i.order_id WHERE o.id = ?', (order_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_order_with_items_and_customer(self, order_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT o.*, c.name as customer_name, c.email as customer_email, oi.product_id, oi.quantity FROM orders o JOIN customers c ON o.customer_id = c.id JOIN order_items oi ON o.id = oi.order_id WHERE o.id = ?', (order_id,)).fetchone()
            if rows is None:
                raise OrderNotFoundError(f'Order with id {order_id} not found')
            return dict(rows)

    def get_orders_with_customer_and_product_details(self, order_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT o.*, c.name as customer_name, c.email as customer_email, p.name as product_name, p.price, p.category_id FROM orders o JOIN customers c ON o.customer_id = c.id JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id WHERE o.id = ?', (order_id,)).fetchone()
            if rows is None:
                raise OrderNotFoundError(f'Order with id {order_id} not found')
            return dict(rows)

