"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CustomerNotFoundError
from models import Customer, Product


class CustomerRepository:
    """SQLite repository for Customer over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, customer: Customer) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
                (customer.name, customer.email, customer.phone),
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

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, phone: Optional[Any] = None, max_price: Optional[Any] = None, min_price: Optional[Any] = None, min_stock: Optional[Any] = None) -> List[Customer]:
        with self.db.connect() as conn:
            query = "SELECT * FROM customers WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
            if max_price is not None:
                query += ' AND id <= ?'
                params.append(max_price)
            if min_price is not None:
                query += ' AND id >= ?'
                params.append(min_price)
            if min_stock is not None:
                query += ' AND id >= ?'
                params.append(min_stock)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'phone']
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

    def get_customer_orders_with_invoices(self, customer_id: int, status_filter: str, date_from: datetime, date_to: datetime) -> list[dict]:
        return []

    def get_customer_order_count_by_status(self, customer_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT o.status, COUNT(*) AS count\n                FROM orders o\n                WHERE o.customer_id = ?\n                GROUP BY o.status\n                ', (customer_id,)).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_customer_total_spent(self, customer_id: int, date_from: datetime, date_to: datetime) -> float:
        return 0.0

    def get_customer_most_purchased_product(self, customer_id: int, date_from: datetime, date_to: datetime) -> Product:
        return None

    def search_orders_by_customer_email(self, email: str, status_filter: str, date_from: datetime, date_to: datetime) -> list[dict]:
        return []

    def get_customer_order_summary(self, customer_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute("\n                SELECT \n                    COUNT(*) AS total_orders,\n                    SUM(CASE WHEN o.status = 'completed' THEN 1 ELSE 0 END) AS completed_orders,\n                    SUM(CASE WHEN o.status = 'pending' THEN 1 ELSE 0 END) AS pending_orders,\n                    SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_orders\n                FROM orders o\n                WHERE o.customer_id = ?\n                ", (customer_id,)).fetchone()
            return {'total_orders': rows[0], 'completed_orders': rows[1], 'pending_orders': rows[2], 'cancelled_orders': rows[3]}

