"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CustomerNotFoundError
from models import Customer


class CustomerRepository:
    """SQLite repository for Customer over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, customer: Customer) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO customers (name, email, phone, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (customer.name, customer.email, customer.phone, customer.created_at, customer.updated_at),
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

    def list(self, email: Optional[Any] = None, name: Optional[Any] = None, phone: Optional[Any] = None) -> List[Customer]:
        with self.db.connect() as conn:
            query = "SELECT * FROM customers WHERE 1=1"
            params: List[Any] = []
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'phone', 'created_at', 'updated_at']
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

    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        return self.list(
            email=email,
        )

    def get_customer_by_phone(self, phone: str) -> Optional[Customer]:
        return self.list(
            phone=phone,
        )

    def get_customers_with_order_count(self) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT c.id, c.name, c.email, c.phone, c.created_at, c.updated_at FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id', ()).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_with_total_spent(self) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT c.id, c.name, c.email, c.phone, c.created_at, c.updated_at FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id', ()).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_by_status_filter(self, status: str) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM customers WHERE id IN (SELECT customer_id FROM orders WHERE status = ?)', (status,)).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_in_date_range(self, start_date: datetime, end_date: datetime) -> list[Customer]:
        return []

    def get_customer_orders_summary(self, customer_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) as order_count, SUM(total_amount) as total_spent FROM orders WHERE customer_id = ?', (customer_id,)).fetchone()
            return {'order_count': row[0] if row[0] is not None else 0, 'total_spent': row[1] if row[1] is not None else 0}

    def get_active_customers_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM customers",
            ).fetchone()
            return int(row["n"])

    def get_customers_with_pending_orders(self) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT DISTINCT c.id, c.name, c.email, c.phone, c.created_at, c.updated_at FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.status = ?', ('pending',)).fetchall()
            return [Customer(**dict(r)) for r in rows]

