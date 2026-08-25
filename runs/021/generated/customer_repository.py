"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CustomerNotFoundError
from models import Customer, Order


class CustomerRepository:
    """SQLite repository for Customer over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, customer: Customer) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO customers (name, email) VALUES (?, ?)",
                (customer.name, customer.email),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Customer]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ?", (id,)
            ).fetchone()
            return Customer(**dict(row)) if row else None

    def get_all(self) -> List[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM customers ORDER BY id"
            ).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def list(self) -> List[Customer]:
        return self.get_all()

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE customers SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise CustomerNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM customers WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_customer_orders_with_status_filter(self, customer_id: int, status: str) -> list[Order]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM orders WHERE customer_id = ? AND status = ?', (customer_id, status))
            rows = cursor.fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_customer_orders_with_date_range(self, customer_id: int, start_date: str, end_date: str) -> list[Order]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM orders WHERE customer_id = ? AND order_date BETWEEN ? AND ?', (customer_id, start_date, end_date))
            rows = cursor.fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_customer_order_count_by_status(self, customer_id: int) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT status, COUNT(*) as count FROM orders WHERE customer_id = ? GROUP BY status', (customer_id,))
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    def get_customer_total_orders_and_revenue(self, customer_id: int) -> dict[str, any]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as total_orders, 0 as revenue FROM orders WHERE customer_id = ?', (customer_id,))
            row = cursor.fetchone()
            return {'total_orders': row[0], 'revenue': row[1]}

    def get_customer_orders_with_pagination(self, customer_id: int, page: int, page_size: int) -> dict[str, any]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * page_size
            cursor.execute('SELECT * FROM orders WHERE customer_id = ? ORDER BY order_date DESC LIMIT ? OFFSET ?', (customer_id, page_size, offset))
            rows = cursor.fetchall()
            return {'orders': [Order(**dict(r)) for r in rows], 'page': page, 'page_size': page_size}

