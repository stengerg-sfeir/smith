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

    def find_budgets_by_month(self, month: str) -> List[Budget]:
        return self.list(month=month)

    def find_budgets_by_category(self, category_id: int) -> List[Budget]:
        return self.list(category_id=category_id)

    def find_budgets_by_month_and_category(self, category_id: int, month: str) -> List[Budget]:
        return self.list(category_id=category_id, month=month)

    def get_budget_amount_for_category_in_month(self, category_id: int, month: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT amount_limit_cents FROM budgets WHERE category_id = ? AND month = ?",
                (category_id, month)
            ).fetchone()
            return row[0] if row else 0

    def check_budget_exceeded_after_insert(self, expense: Expense) -> bool:
        # This method assumes we have access to expense details and can check against existing budgets
        # We need to determine if the expense exceeds the budget for its category and month
        # Since we don't have Expense model in scope, this is a placeholder
        # In a real implementation, we would need to know the category_id and month of the expense
        # and check against the budget for that category and month
        raise NotImplementedError("Expense model not available in context")

    def get_budget_status_for_category_in_month(self, category_id: int, month: str) -> str:
        # Check if budget exists for category and month
        budget = self.get_by_category_and_month(category_id, month)
        if not budget:
            return "No Budget"

        # If budget exists, check if it's exceeded (assuming we have expense data)
        # This method is incomplete without expense data
        return "Within Budget"  # Placeholder

    def get_monthly_budget_summary(self, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            # Get all budgets for the given month
            rows = conn.execute(
                "SELECT category_id, amount_limit_cents FROM budgets WHERE month = ? ORDER BY category_id",
                (month,)
            ).fetchall()

            # Group by category_id and sum up amounts (though each budget has a single amount)
            summary = {}
            for row in rows:
                category_id = row[0]
                amount = row[1]
                summary[category_id] = {
                    "amount_limit_cents": amount,
                    "status": "Within Budget"  # Placeholder
                }
            return summary

    def get_budgets_for_all_categories_in_month(self, month: str) -> Dict[int, Budget]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM budgets WHERE month = ? ORDER BY category_id",
                (month,)
            ).fetchall()
            result = {}
            for row in rows:
                result[row[0]] = Budget(**dict(row))
            return result

