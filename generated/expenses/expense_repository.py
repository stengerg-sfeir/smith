"""ExpenseRepository data access."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from database import Database
from exceptions import ExpenseNotFoundError
from models import Expense


class ExpenseRepository:
    """SQLite repository for Expense over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, expense: Expense) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO expenses (amount_cents, description, expense_date, category_id, payment_method, is_recurring) VALUES (?, ?, ?, ?, ?, ?)",
                (expense.amount_cents, expense.description, expense.expense_date, expense.category_id, expense.payment_method, expense.is_recurring),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Expense]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM expenses WHERE id = ?", (id,)
            ).fetchone()
            return Expense(**dict(row)) if row else None

    def get_all(self) -> List[Expense]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM expenses ORDER BY id"
            ).fetchall()
            return [Expense(**dict(r)) for r in rows]

    def list(self, category_id: Optional[Any] = None, payment_method: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Expense]:
        with self.db.connect() as conn:
            query = "SELECT * FROM expenses WHERE 1=1"
            params: List[Any] = []
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            if payment_method is not None:
                query += ' AND payment_method = ?'
                params.append(payment_method)
            if start_date is not None:
                query += ' AND expense_date >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND expense_date <= ?'
                params.append(end_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Expense(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['amount_cents', 'description', 'expense_date', 'category_id', 'payment_method', 'is_recurring']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE expenses SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ExpenseNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM expenses WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def find_expenses_by_date_range(self, start_date: date, end_date: date) -> List[Expense]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def find_expenses_by_category(self, category_id: int) -> List[Expense]:
        return self.list(category_id=category_id)

    def find_expenses_by_payment_method(self, payment_method: str) -> List[Expense]:
        return self.list(payment_method=payment_method)

    def find_expenses_by_date_and_category(self, start_date: date, end_date: date, category_id: int) -> List[Expense]:
        return self.list(
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
        )

    def find_expenses_by_date_and_payment_method(self, start_date: date, end_date: date, payment_method: str) -> List[Expense]:
        return self.list(
            payment_method=payment_method,
            start_date=start_date,
            end_date=end_date,
        )

    def find_expenses_by_all_filters(self, start_date: date, end_date: date, category_id: int, payment_method: str) -> List[Expense]:
        return self.list(
            category_id=category_id,
            payment_method=payment_method,
            start_date=start_date,
            end_date=end_date,
        )

    def get_total_expense_amount_by_month(self, month: str) -> int:
        with self.db.connect() as conn:
            # Assuming month format is 'YYYY-MM'
            query = "SELECT SUM(amount_cents) FROM expenses WHERE strftime('%Y-%m', expense_date) = ?"
            result = conn.execute(query, (month,)).fetchone()
            return result[0] if result[0] is not None else 0

    def get_category_spending_breakdown_by_month(self, month: str) -> Dict[str, int]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    category_id,
                    SUM(amount_cents) AS total_amount
                FROM expenses 
                WHERE strftime('%Y-%m', expense_date) = ?
                GROUP BY category_id
            """
            rows = conn.execute(query, (month,)).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_budget_status_for_category_in_month(self, category_id: int, month: str) -> str:
        with self.db.connect() as conn:
            # Get total spending for category in month
            query = """
                SELECT SUM(amount_cents) AS total_spent
                FROM expenses 
                WHERE category_id = ? 
                  AND strftime('%Y-%m', expense_date) = ?
            """
            result = conn.execute(query, (category_id, month)).fetchone()
            total_spent = result[0] if result[0] is not None else 0

            # Assuming we have a budget value stored in a separate table or config
            # For now, we'll simulate with a placeholder - in real app, this would come from budget table
            # Example: if budget is 1000, and spent is 800, return "Under Budget"
            # This is a placeholder - actual implementation would require budget data
            budget_amount = 1000  # Placeholder - should come from budget table
            if total_spent > budget_amount:
                return "Over Budget"
            elif total_spent == budget_amount:
                return "At Budget"
            else:
                return "Under Budget"

    def get_monthly_budget_summary(self, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    category_id,
                    SUM(amount_cents) AS total_spent,
                    MAX(expense_date) AS latest_expense_date
                FROM expenses 
                WHERE strftime('%Y-%m', expense_date) = ?
                GROUP BY category_id
            """
            rows = conn.execute(query, (month,)).fetchall()
            return {
                'month': month,
                'category_spending': {row[0]: row[1] for row in rows},
                'total_spent': sum(row[1] for row in rows),
                'total_categories': len(rows)
            }

    def get_expenses_for_category_with_aggregates(self, category_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    category_id,
                    SUM(amount_cents) AS total_amount,
                    COUNT(*) AS expense_count,
                    MIN(expense_date) AS first_expense_date,
                    MAX(expense_date) AS last_expense_date,
                    AVG(amount_cents) AS average_amount
                FROM expenses 
                WHERE category_id = ? 
                  AND expense_date >= ? 
                  AND expense_date <= ?
                GROUP BY category_id
            """
            row = conn.execute(query, (category_id, start_date, end_date)).fetchone()
            return {
                'category_id': category_id,
                'total_amount': row[1] if row[1] is not None else 0,
                'expense_count': row[2] if row[2] is not None else 0,
                'first_expense_date': row[3] if row[3] is not None else None,
                'last_expense_date': row[4] if row[4] is not None else None,
                'average_amount': row[5] if row[5] is not None else 0
            }

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    strftime('%Y', expense_date) AS year,
                    strftime('%m', expense_date) AS month,
                    SUM(amount_cents) AS monthly_total
                FROM expenses 
                WHERE strftime('%Y', expense_date) = ?
                GROUP BY month
                ORDER BY month
            """
            rows = conn.execute(query, (str(year),)).fetchall()
            monthly_totals = {}
            for row in rows:
                month = row[1]
                total = row[2]
                monthly_totals[month] = total

            return {
                'year': str(year),
                'monthly_totals': monthly_totals,
                'total_yearly_spending': sum(monthly_totals.values()) if monthly_totals else 0
            }

    def check_budget_exceeded_after_insert(self, expense: Expense) -> bool:
        # This would require knowledge of the budget system
        # For now, we'll simulate a simple check based on category and month
        with self.db.connect() as conn:
            # Get current total spending for the category in the same month
            month = expense.expense_date.strftime('%Y-%m')
            query = """
                SELECT SUM(amount_cents) AS total_spent
                FROM expenses 
                WHERE category_id = ? 
                  AND strftime('%Y-%m', expense_date) = ?
            """
            result = conn.execute(query, (expense.category_id, month)).fetchone()
            total_spent = result[0] if result[0] is not None else 0

            # Assume budget is 1000 cents (10 dollars) - this should come from a budget table
            budget_amount = 1000
            return total_spent + expense.amount_cents > budget_amount

    def find_recurring_expenses(self, start_date: date, end_date: date) -> List[Expense]:
        with self.db.connect() as conn:
            query = """
                SELECT * FROM expenses 
                WHERE is_recurring = 1 
                  AND expense_date >= ? 
                  AND expense_date <= ?
            """
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            return [Expense(**dict(r)) for r in rows]

    def get_expense_count_by_category(self, start_date: date, end_date: date) -> Dict[int, int]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    category_id,
                    COUNT(*) AS count
                FROM expenses 
                WHERE expense_date >= ? 
                  AND expense_date <= ?
                GROUP BY category_id
            """
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            return {row[0]: row[1] for row in rows}

