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

    def list(self, category_id: Optional[Any] = None, month: Optional[Any] = None) -> List[Budget]:
        with self.db.connect() as conn:
            query = "SELECT * FROM budgets WHERE 1=1"
            params: List[Any] = []
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            if month is not None:
                query += ' AND month = ?'
                params.append(month)
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

    def find_budgets_by_month(self, month: str, category_id: Optional[int] = None) -> List[Budget]:
        return self.list(month=month)

    def find_budgets_by_category(self, category_id: int, start_month: Optional[str] = None, end_month: Optional[str] = None) -> List[Budget]:
        # Filter by category_id only, as the original list method already handles filtering
        return self.list(category_id=category_id)

    def get_budget_by_category_and_month(self, category_id: int, month: str) -> Optional[Budget]:
        return self.get_by_category_and_month(category_id, month)

    def check_budget_exceeded(self, category_id: int, month: str) -> bool:
        # This would require access to spending data (not in the Budget model)
        # Since we don't have spending data in the repository, we can't determine if budget is exceeded
        # This method is not implementable without spending data
        raise NotImplementedError()

    def get_budget_status_for_month(self, category_id: int, month: str) -> str:
        # Without spending data, we cannot determine status
        # This method requires spending data to compare against budget
        raise NotImplementedError()

    def get_total_budget_for_category(self, category_id: int) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "SELECT SUM(amount_limit_cents) FROM budgets WHERE category_id = ?", (category_id,)
            )
            total = cursor.fetchone()[0]
            return total or 0

    def get_monthly_budget_spending_summary(self, start_month: str, end_month: str) -> Dict[str, Any]:
        # This requires spending data which is not available in the Budget model
        # Without spending data, we cannot generate a spending summary
        raise NotImplementedError()

    def get_budgets_for_period(self, start_month: str, end_month: str) -> List[Budget]:
        # Filter budgets within a given month range
        with self.db.connect() as conn:
            # Assuming month format is YYYY-MM
            query = "SELECT * FROM budgets WHERE month BETWEEN ? AND ? ORDER BY month"
            rows = conn.execute(query, (start_month, end_month)).fetchall()
            return [Budget(**dict(r)) for r in rows]

