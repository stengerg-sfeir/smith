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

    def list(self, name: Optional[Any] = None, email_domain: Optional[Any] = None, email: Optional[Any] = None, phone: Optional[Any] = None) -> List[Customer]:
        with self.db.connect() as conn:
            query = "SELECT * FROM customers WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if email_domain is not None:
                query += ' AND email = ?'
                params.append(email_domain)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
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

    def get_customers_by_domain(self, domain: str) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE email LIKE ?', (f'%{domain}@',))
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customer_count_by_domain(self, domain: str) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM customers WHERE email LIKE ?', (f'%{domain}@',))
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_customers_with_email_pattern(self, pattern: str) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE email LIKE ?', (f'%{pattern}%',))
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_with_name_containing(self, substring: str) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE name LIKE ?', (f'%{substring}%',))
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_with_phone_prefix(self, prefix: str) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE phone LIKE ?', (f'{prefix}%',))
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_total_customers(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM customers')
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_customers_with_valid_email_format(self) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customers WHERE email LIKE '%@%' AND email NOT LIKE '%@%.%'")
            cursor.execute("SELECT * FROM customers WHERE email LIKE '%@%' AND email LIKE '%@%.%'")
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_by_name_and_domain(self, name: str, domain: str) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE name LIKE ? AND email LIKE ?', (f'%{name}%', f'%{domain}@'))
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

