"""PurchaseRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import PurchaseNotFoundError
from models import Purchase


class PurchaseRepository:
    """SQLite repository for Purchase over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, purchase: Purchase) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO purchases (customer_id, amount, purchase_date) VALUES (?, ?, ?)",
                (purchase.customer_id, purchase.amount, purchase.purchase_date),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Purchase]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM purchases WHERE id = ?", (id,)
            ).fetchone()
            return Purchase(**dict(row)) if row else None

    def get_all(self) -> List[Purchase]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM purchases ORDER BY id"
            ).fetchall()
            return [Purchase(**dict(r)) for r in rows]

    def list(self, customer_id: Optional[Any] = None, amount: Optional[Any] = None, purchase_date: Optional[Any] = None) -> List[Purchase]:
        with self.db.connect() as conn:
            query = "SELECT * FROM purchases WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if amount is not None:
                query += ' AND amount >= ?'
                params.append(amount)
            if purchase_date is not None:
                query += ' AND purchase_date >= ?'
                params.append(purchase_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Purchase(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'amount', 'purchase_date']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE purchases SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise PurchaseNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM purchases WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_customer_purchase_total(self, customer_id: int) -> float:
        return self.list(
            customer_id=customer_id,
        )

    def get_customer_purchase_history(self, customer_id: int, start_date: datetime, end_date: datetime) -> list[Purchase]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM purchases r JOIN customers o ON r.customer_id = o.id WHERE o.name = ? AND r.purchase_date >= ? AND r.purchase_date <= ?",
                (customer_id, start_date, end_date)
            ).fetchall()
            return [Purchase(**dict(r)) for r in rows]

    def get_customer_spending_trend(self, customer_id: int, period: str) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM purchases r JOIN customers o ON r.customer_id = o.id WHERE o.id = ?",
                (customer_id,)
            ).fetchall()
            return [Purchase(**dict(r)) for r in rows]

    def get_top_spending_customers(self, time_range: str, limit: int) -> list[dict[str, any]]:
        start_date = time_range
        end_date = time_range
        if '-' not in time_range:
            start_date = f'{time_range}-01-01'
            end_date = f'{time_range}-12-31'
        elif len(time_range.split('-')) == 2:
            year, month = time_range.split('-')
            start_date = f'{year}-{month}-01'
            end_date = f'{year}-{month}-31'
        query = '\n        SELECT \n            c.id AS customer_id,\n            c.name AS customer_name,\n            c.email AS customer_email,\n            c.phone AS customer_phone,\n            SUM(p.amount) AS total_spent\n        FROM purchases p\n        JOIN customers c ON p.customer_id = c.id\n        WHERE p.purchase_date BETWEEN ? AND ?\n        GROUP BY c.id\n        ORDER BY total_spent DESC\n        LIMIT ?\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (start_date, end_date, limit)).fetchall()
        return [dict(row) for row in rows]

