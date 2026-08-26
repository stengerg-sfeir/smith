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

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, phone: Optional[Any] = None) -> List[Customer]:
        with self.db.connect() as conn:
            query = "SELECT * FROM customers WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
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

    def get_customer_orders(self, customer_id: int, status: Optional[str]=None, from_date: Optional[str]=None, to_date: Optional[str]=None) -> list[Order]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM orders WHERE customer_id = ?'
            params = [customer_id]
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if from_date is not None:
                query += ' AND order_date >= ?'
                params.append(from_date)
            if to_date is not None:
                query += ' AND order_date <= ?'
                params.append(to_date)
            query += ' ORDER BY order_date DESC'
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_customer_with_orders(self, customer_id: int) -> dict[Customer, list[Order]]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
            customer_row = cursor.fetchone()
            if not customer_row:
                raise CustomerNotFoundError(f'Customer with id {customer_id} not found')
            customer = Customer(**dict(customer_row))
            cursor.execute('SELECT * FROM orders WHERE customer_id = ?', (customer_id,))
            orders_rows = cursor.fetchall()
            orders = [Order(**dict(r)) for r in orders_rows]
            return {customer: orders}

    def get_active_customers_count(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM customers WHERE updated_at >= datetime('now', '-1 year')")
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_customers_by_name_prefix(self, prefix: str) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE name LIKE ?', (f'{prefix}%',))
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customer_total_spent(self, customer_id: int) -> float:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(total_amount) FROM orders WHERE customer_id = ?', (customer_id,))
            result = cursor.fetchone()
            total = result[0] if result[0] is not None else 0.0
            return float(total)

    def get_customer_order_summary(self, customer_id: int) -> dict[str, float]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT \n                    status,\n                    SUM(total_amount) as total_spent\n                FROM orders \n                WHERE customer_id = ?\n                GROUP BY status\n            ', (customer_id,))
            rows = cursor.fetchall()
            return {row[0]: float(row[1]) for row in rows}

