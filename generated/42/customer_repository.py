"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CustomerNotFoundError
from models import Customer, Purchase


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

    def get_customer_purchase_total(self, customer_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute('SELECT SUM(amount) FROM purchases WHERE customer_id = ?', (customer_id,)).fetchone()
            return row[0] if row[0] is not None else 0.0

    def get_customer_purchase_history(self, customer_id: int, start_date: str, end_date: str) -> list[Purchase]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM purchases WHERE customer_id = ? AND purchase_date BETWEEN ? AND ?', (customer_id, start_date, end_date)).fetchall()
            return [Purchase(**dict(r)) for r in rows]

    def get_customer_spending_trend(self, customer_id: int, period: str) -> dict[str, float]:
        with self.db.connect() as conn:
            if period == 'monthly':
                rows = conn.execute('SELECT substr(purchase_date, 1, 7) as month, SUM(amount) as total FROM purchases WHERE customer_id = ? GROUP BY substr(purchase_date, 1, 7)', (customer_id,)).fetchall()
            elif period == 'yearly':
                rows = conn.execute('SELECT substr(purchase_date, 1, 4) as year, SUM(amount) as total FROM purchases WHERE customer_id = ? GROUP BY substr(purchase_date, 1, 4)', (customer_id,)).fetchall()
            else:
                raise ValueError("Period must be 'monthly' or 'yearly'")
            return {row[0]: row[1] for row in rows}

    def get_top_spending_customers(self, time_range: str, limit: int) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            if time_range == 'last_year':
                query = '\n                    SELECT c.id, c.name, SUM(p.amount) as total_spent\n                    FROM customers c\n                    JOIN purchases p ON c.id = p.customer_id\n                    WHERE substr(p.purchase_date, 1, 4) = ?\n                    GROUP BY c.id, c.name\n                    ORDER BY total_spent DESC\n                    LIMIT ?\n                '
                rows = conn.execute(query, (str(2024), limit)).fetchall()
            elif time_range == 'last_month':
                query = '\n                    SELECT c.id, c.name, SUM(p.amount) as total_spent\n                    FROM customers c\n                    JOIN purchases p ON c.id = p.customer_id\n                    WHERE substr(p.purchase_date, 1, 7) = ?\n                    GROUP BY c.id, c.name\n                    ORDER BY total_spent DESC\n                    LIMIT ?\n                '
                rows = conn.execute(query, (str(202401), limit)).fetchall()
            else:
                raise ValueError("Time range must be 'last_year' or 'last_month'")
            return [dict(id=row[0], name=row[1], total_spent=row[2]) for row in rows]

