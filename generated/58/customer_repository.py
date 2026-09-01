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

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None) -> List[Customer]:
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

    def get_customer_with_external_data(self, customer_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM customers WHERE id = ?', (customer_id,)).fetchone()
            if row is None:
                raise CustomerNotFoundError(f'Customer with id {customer_id} not found')
            return dict(row)

    def list_customers_with_external_info(self, name_filter: str, email_filter: str, phone_filter: str, page: int, page_size: int) -> list[dict]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM customers WHERE 1=1'
            params = []
            if name_filter:
                query += ' AND name LIKE ?'
                params.append(f'%{name_filter}%')
            if email_filter:
                query += ' AND email LIKE ?'
                params.append(f'%{email_filter}%')
            if phone_filter:
                query += ' AND phone LIKE ?'
                params.append(f'%{phone_filter}%')
            query += ' ORDER BY name LIMIT ? OFFSET ?'
            params.extend([str(page_size), str((page - 1) * page_size)])
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_customer_total_count(self, name_filter: str, email_filter: str) -> int:
        with self.db.connect() as conn:
            query = 'SELECT COUNT(*) FROM customers WHERE 1=1'
            params = []
            if name_filter:
                query += ' AND name LIKE ?'
                params.append(f'%{name_filter}%')
            if email_filter:
                query += ' AND email LIKE ?'
                params.append(f'%{email_filter}%')
            count = conn.execute(query, params).fetchone()[0]
            return count

    def generate_customer_report(self, start_date: datetime, end_date: datetime, region: str) -> dict:
        return {}

    def get_customer_by_email(self, email: str) -> dict:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM customers WHERE email = ?', (email,)).fetchone()
            if row is None:
                raise CustomerNotFoundError(f'Customer with email {email} not found')
            return dict(row)

