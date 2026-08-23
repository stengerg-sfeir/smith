"""BudgetRepository data access."""
from __future__ import annotations

from datetime import date
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

    def list(self, category: Optional[Any] = None, month: Optional[Any] = None, category_id: Optional[Any] = None) -> List[Budget]:
        with self.db.connect() as conn:
            query = "SELECT * FROM budgets WHERE 1=1"
            params: List[Any] = []
            if category is not None:
                query += ' AND category_id = ?'
                params.append(category)
            if month is not None:
                query += ' AND month = ?'
                params.append(month)
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
        budgets = self.list(category_id=category_id, month=month)
        if not budgets:
            return {
                "category_id": category_id,
                "month": month,
                "total_budget": 0,
                "total_spent": 0,
                "is_over_budget": False
            }

        # Assuming we have a way to calculate spent amount (not provided in models)
        # This is a placeholder - actual implementation would require spending data
        total_budget = sum(b.amount_limit_cents for b in budgets)
        total_spent = 0  # Placeholder - would need actual spending data
        is_over_budget = total_spent > total_budget

        return {
            "category_id": category_id,
            "month": month,
            "total_budget": total_budget,
            "total_spent": total_spent,
            "is_over_budget": is_over_budget
        }

    def check_budget_exceeded(self, category_id: int, month: str) -> bool:
        budgets = self.list(category_id=category_id, month=month)
        if not budgets:
            return False

        # Placeholder - actual implementation would require spending data
        # This assumes we have a way to calculate total spent
        # Since we don't have spending data, we can't determine if budget is exceeded
        # This method is currently incomplete without spending data
        return False

    def get_budget_by_category_and_month(self, category_id: int, month: str) -> Optional[Budget]:
        return self.get_by_category_and_month(category_id, month)

    def list_budgets_with_category_summary(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Dict[str, Any]]:
        # Placeholder implementation - requires spending data to calculate category summaries
        # This method would normally aggregate budgets by category and month
        # and include total budget, total spent, etc.

        # Without spending data, we can only return basic budget info
        # This is a minimal implementation that returns all budgets with category and month
        budgets = self.get_all()

        result = []
        for budget in budgets:
            result.append({
                "category_id": budget.category_id,
                "month": budget.month,
                "amount_limit_cents": budget.amount_limit_cents
            })

        return result

