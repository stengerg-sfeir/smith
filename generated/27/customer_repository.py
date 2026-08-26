"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
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

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, phone: Optional[Any] = None) -> List[Customer]:
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
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM customers WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_customer_by_id(self, customer_id: int) -> Optional[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return Customer(**dict(row))

    def list_customers(self) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM customers')
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def list_customers_by_email(self, email: str) -> list[Customer]:
        return self.list(
            email=email,
        )

    def list_customers_with_reservation_count(self) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT c.id, c.name, c.email, c.phone, \n                (SELECT COUNT(*) FROM reservations r WHERE r.customer_id = c.id) AS reservation_count\n                FROM customers c\n                ORDER BY c.id\n            ')
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_total_customers(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM customers')
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_customers_with_active_reservations(self) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("\n                SELECT DISTINCT c.*\n                FROM customers c\n                JOIN reservations r ON c.id = r.customer_id\n                WHERE r.status = 'active'\n            ")
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_with_reservations_in_date_range(self, start_date: str, end_date: str) -> list[Customer]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT DISTINCT c.*\n                FROM customers c\n                JOIN reservations r ON c.id = r.customer_id\n                WHERE r.start_date BETWEEN ? AND ?\n            ', (start_date, end_date))
            rows = cursor.fetchall()
            return [Customer(**dict(r)) for r in rows]

