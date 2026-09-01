"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, List, Optional

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

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, phone: Optional[Any] = None, max_discount_amount: Optional[Any] = None, max_price: Optional[Any] = None, max_quantity: Optional[Any] = None, max_rate: Optional[Any] = None, max_stock: Optional[Any] = None, min_order_amount: Optional[Any] = None, min_price: Optional[Any] = None, min_quantity: Optional[Any] = None, min_rate: Optional[Any] = None, min_stock: Optional[Any] = None) -> List[Customer]:
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
            if max_discount_amount is not None:
                query += ' AND id <= ?'
                params.append(max_discount_amount)
            if max_price is not None:
                query += ' AND id <= ?'
                params.append(max_price)
            if max_quantity is not None:
                query += ' AND id <= ?'
                params.append(max_quantity)
            if max_rate is not None:
                query += ' AND id <= ?'
                params.append(max_rate)
            if max_stock is not None:
                query += ' AND id <= ?'
                params.append(max_stock)
            if min_order_amount is not None:
                query += ' AND id >= ?'
                params.append(min_order_amount)
            if min_price is not None:
                query += ' AND id >= ?'
                params.append(min_price)
            if min_quantity is not None:
                query += ' AND id >= ?'
                params.append(min_quantity)
            if min_rate is not None:
                query += ' AND id >= ?'
                params.append(min_rate)
            if min_stock is not None:
                query += ' AND id >= ?'
                params.append(min_stock)
            rows = conn.execute(query, params).fetchall()
            return [Customer(**dict(r)) for r in rows]
