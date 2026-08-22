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

    def list_expenses_filtered(self, category_id: Optional[int] = None, start_date: Optional[date] = None, end_date: Optional[date] = None, payment_method: Optional[str] = None) -> List[Expense]:
        return self.list(
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
            payment_method=payment_method,
        )

    def get_expenses_by_category(self, category_id: int) -> List[Expense]:
        return self.list(category_id=category_id)

    def get_monthly_spending_summary(self, month: str) -> Dict[str, Any]:
        # Format: "YYYY-MM"
        year, month_num = month.split('-')
        month_num = int(month_num)

        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    strftime('%Y-%m', expense_date) as month,
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE strftime('%Y-%m', expense_date) = ?
                GROUP BY strftime('%Y-%m', expense_date)
                """,
                (month,)
            )
            row = cursor.fetchone()
            if row is None:
                return {"month": month, "total_spent": 0}
            return {"month": month, "total_spent": row[1]}

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    strftime('%Y', expense_date) as year,
                    strftime('%m', expense_date) as month,
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE strftime('%Y', expense_date) = ?
                GROUP BY strftime('%Y', expense_date), strftime('%m', expense_date)
                ORDER BY month
                """,
                (str(year),)
            )
            result = {}
            for row in cursor.fetchall():
                month = f"{year}-{str(row[1]).zfill(2)}"
                result[month] = row[2]
            return {"year": str(year), "monthly_spending": result}

    def get_category_spending_range(self, category_id: int, start_date: date, end_date: date) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE category_id = ? 
                AND expense_date >= ? 
                AND expense_date <= ?
                """,
                (category_id, start_date, end_date)
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def check_budget_exceeded(self, category_id: int, month: str) -> bool:
        # Format: "YYYY-MM"
        year, month_num = month.split('-')
        month_num = int(month_num)

        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE category_id = ? 
                AND strftime('%Y-%m', expense_date) = ?
                """,
                (category_id, month)
            )
            row = cursor.fetchone()
            total_spent = row[0] if row else 0
            # Assuming budget is stored in a separate table or config
            # For now, we'll simulate a budget check with a hardcoded value
            # In a real app, this would query a budget table
            budget = 1000  # Example budget value
            return total_spent > budget

    def get_budget_status_for_month(self, category_id: int, month: str) -> Dict[str, Any]:
        # Format: "YYYY-MM"
        year, month_num = month.split('-')
        month_num = int(month_num)

        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    strftime('%Y-%m', expense_date) as month,
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE category_id = ? 
                AND strftime('%Y-%m', expense_date) = ?
                GROUP BY strftime('%Y-%m', expense_date)
                """,
                (category_id, month)
            )
            row = cursor.fetchone()
            total_spent = row[1] if row else 0
            # Assuming budget is stored in a separate table or config
            budget = 1000  # Example budget value

            return {
                "category_id": category_id,
                "month": month,
                "total_spent": total_spent,
                "budget": budget,
                "is_over_budget": total_spent > budget
            }

    def get_recurring_expense_patterns(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    category_id,
                    payment_method,
                    COUNT(*) as recurrence_count,
                    AVG(amount_cents) as avg_amount,
                    MIN(expense_date) as first_occurrence,
                    MAX(expense_date) as last_occurrence
                FROM expenses 
                WHERE is_recurring = 1
                GROUP BY category_id, payment_method
                ORDER BY recurrence_count DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "category_id": row[0],
                    "payment_method": row[1],
                    "recurrence_count": row[2],
                    "avg_amount": row[3],
                    "first_occurrence": row[4],
                    "last_occurrence": row[5]
                }
                for row in rows
            ]

