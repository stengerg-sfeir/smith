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

    def get_customers_with_account_balance_over_threshold(self, threshold: float) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM accounts WHERE balance > ?', (threshold,)).fetchall()
            return [dict(r) for r in rows]

    def get_customers_by_phone_pattern(self, pattern: str) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM customers WHERE phone LIKE ?', (pattern,)).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customer_with_most_total_transactions(self) -> Optional[Customer]:
        with self.db.connect() as conn:
            return None

    def get_customers_with_active_accounts_and_balance_range(self, min_balance: float, max_balance: float) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM accounts WHERE balance BETWEEN ? AND ?', (min_balance, max_balance)).fetchall()
            return [dict(r) for r in rows]

    def get_total_deposit_volume_by_customer(self) -> dict[int, float]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT account_id, SUM(amount) AS total_deposit FROM deposits GROUP BY account_id').fetchall()
            result = {}
            for row in rows:
                result[row['account_id']] = row['total_deposit']
            return result

    def get_customers_with_recent_activity(self, days_ago: int, min_transaction_amount: float) -> list[Customer]:
        with self.db.connect() as conn:
            return []

    def get_customer_account_summary_with_transaction_count(self, customer_id: int) -> dict[str, any]:
        with self.db.connect() as conn:
            return {}

