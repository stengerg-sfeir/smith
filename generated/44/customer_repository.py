"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CustomerNotFoundError
from models import Customer, Sale


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

    def get_customers_with_unverified_email(self) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM customers WHERE email IS NULL OR email NOT LIKE ?', ('_%@_%._%',)).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_sales_by_customer(self, customer_id: int, start_date: str, end_date: str) -> list[Sale]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM sales WHERE customer_id = ? AND sale_date BETWEEN ? AND ?', (customer_id, start_date, end_date)).fetchall()
            return [Sale(**dict(r)) for r in rows]

    def get_total_sales_amount_by_customer(self, customer_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute('SELECT SUM(total_price) FROM sales WHERE customer_id = ?', (customer_id,)).fetchone()
            return row[0] if row[0] is not None else 0.0

    def get_top_customers_by_purchase_count(self, limit: int) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM customers LIMIT ?",
                (limit,)
            ).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customers_with_recent_activity(self, days_ago: int) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM customers WHERE updated_at >= datetime('now', '-' || ? || ' days')",
                (days_ago,)
            ).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customer_orders_summary(self, customer_id: int) -> dict[str, any]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT \n                    COUNT(*) AS order_count,\n                    SUM(sale_date) AS total_sales_date,\n                    SUM(total_price) AS total_sales_amount\n                FROM sales \n                WHERE customer_id = ?\n                ', (customer_id,)).fetchall()
            result = {}
            for r in rows:
                result['order_count'] = r[0]
                result['total_sales_date'] = r[1] if r[1] is not None else ''
                result['total_sales_amount'] = r[2] if r[2] is not None else 0.0
            return result

