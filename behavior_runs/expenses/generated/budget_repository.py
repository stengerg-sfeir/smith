"""BudgetRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Budget


class BudgetRepository:
    """SQLite repository for Budget over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, budget: Budget) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO budgets (category_id, month, amount_limit_cents) VALUES (?, ?, ?)",
                (budget.category_id, budget.month, budget.amount_limit_cents),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Budget]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM budgets WHERE id = ?", (id,)
            ).fetchone()
            return Budget(**dict(row)) if row else None

    def get_all(self) -> List[Budget]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM budgets ORDER BY id"
            ).fetchall()
            return [Budget(**dict(r)) for r in rows]

    def list(self, category: Optional[Any] = None, month: Optional[Any] = None, amount_limit_cents: Optional[Any] = None, category_id: Optional[Any] = None) -> List[Budget]:
        with self.db.connect() as conn:
            query = "SELECT * FROM budgets WHERE 1=1"
            params: List[Any] = []
            if category is not None:
                query += ' AND category_id = ?'
                params.append(category)
            if month is not None:
                query += ' AND month = ?'
                params.append(month)
            if amount_limit_cents is not None:
                query += ' AND amount_limit_cents = ?'
                params.append(amount_limit_cents)
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Budget(**dict(r)) for r in rows]

    def get_by_category_and_month(self, category_id: Any, month: Any) -> Optional[Budget]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM budgets WHERE category_id = ? AND month = ?", (category_id, month)
            ).fetchone()
            return Budget(**dict(row)) if row else None

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['category_id', 'month', 'amount_limit_cents']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE budgets SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                return False
            return True

    def delete(self, category_id: Any, month: Any) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM budgets WHERE category_id = ? AND month = ?", (category_id, month)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_budgets_by_month(self, month: str, category_id: Optional[int] = None) -> List[Budget]:
        return self.list(
            month=month,
            category_id=category_id,
        )

    def get_budget_status_for_category_month(self, category_id: int, month: str) -> Dict[str, Any]:
        return self.list(
            category_id=category_id,
            month=month,
        )

    def check_budget_exceeded(self, category_id: int, month: str) -> bool:
        return self.list(
            category_id=category_id,
            month=month,
        )

    def get_budget_by_category_and_month(self, category_id: int, month: str) -> Optional[Budget]:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM budgets WHERE category_id = ? AND month = ?', (category_id, month)).fetchone()
            return Budget(**dict(row)) if row else None

    def list_budgets_with_category_summary(self, start_date: Optional[str]=None, end_date: Optional[str]=None) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            query = 'SELECT b.month, b.amount_limit_cents, c.name AS category_name, c.monthly_budget '
            query += 'FROM budgets b JOIN categories c ON b.category_id = c.id '
            if start_date:
                query += 'WHERE b.month >= ? AND b.month <= ?'
            elif end_date:
                query += 'WHERE b.month <= ?'
            query += ' ORDER BY b.month'
            params = []
            if start_date:
                params.append(start_date)
            if end_date:
                params.append(end_date)
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

