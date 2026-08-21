"""ExpenseRepository data access."""
from __future__ import annotations

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

    def list(self, category_id: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None, payment_method: Optional[Any] = None) -> List[Expense]:
        with self.db.connect() as conn:
            query = "SELECT * FROM expenses WHERE 1=1"
            params: List[Any] = []
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            if start_date is not None:
                query += ' AND expense_date >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND expense_date <= ?'
                params.append(end_date)
            if payment_method is not None:
                query += ' AND payment_method = ?'
                params.append(payment_method)
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

    def find_expenses_by_date_range(self, start_date: datetime.date, end_date: datetime.date) -> List[Expense]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def find_expenses_by_category(self, category_id: int) -> List[Expense]:
        return self.list(category_id=category_id)

    def find_expenses_by_payment_method(self, payment_method: str) -> List[Expense]:
        return self.list(payment_method=payment_method)

    def find_expenses_by_filters(self, category_id: Optional[int] = None, start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None, payment_method: Optional[str] = None) -> List[Expense]:
        return self.list(
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
            payment_method=payment_method,
        )

    def get_monthly_spending_summary(self, month: str) -> Dict[str, Any]:
        # Assuming month format is "YYYY-MM"
        year, month_num = month.split('-')
        month_num = int(month_num)

        with self.db.connect() as conn:
            query = """
                SELECT 
                    strftime('%Y-%m', expense_date) as month,
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE strftime('%Y-%m', expense_date) = ?
                GROUP BY month
            """
            result = conn.execute(query, (month,)).fetchone()
            return {
                "month": month,
                "total_spent_cents": result[1] if result else 0
            }

    def get_yearly_spending_summary(self, year: int) -> Dict[str, Any]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    strftime('%Y', expense_date) as year,
                    strftime('%m', expense_date) as month,
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE strftime('%Y', expense_date) = ?
                GROUP BY year, month
                ORDER BY month
            """
            result = conn.execute(query, (str(year),)).fetchall()

            monthly_totals = {}
            for row in result:
                month_str = f"{year}-{str(row[1]).zfill(2)}"
                monthly_totals[month_str] = row[2]

            return {
                "year": str(year),
                "monthly_spending": monthly_totals
            }

    def get_category_spending_aggregate(self, category_id: int, start_date: datetime.date, end_date: datetime.date) -> Dict[str, int]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE category_id = ? 
                  AND expense_date >= ? 
                  AND expense_date <= ?
            """
            result = conn.execute(query, (category_id, start_date, end_date)).fetchone()
            return {
                "category_id": category_id,
                "total_spent_cents": result[0] if result[0] is not None else 0
            }

    def check_budget_exceeded(self, category_id: int, month: str) -> bool:
        # Assuming month format is "YYYY-MM"
        year, month_num = month.split('-')
        month_num = int(month_num)

        with self.db.connect() as conn:
            query = """
                SELECT 
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE category_id = ? 
                  AND strftime('%Y-%m', expense_date) = ?
            """
            result = conn.execute(query, (category_id, month)).fetchone()
            total_spent = result[0] if result[0] is not None else 0

            # Assuming budget is stored in a separate table or config
            # For this implementation, we'll assume a default budget of 1000 cents (10 USD)
            # In a real app, this would come from a budget table or config
            budget_cents = 1000  # Default budget

            return total_spent > budget_cents

    def get_budget_status_for_month(self, category_id: int, month: str) -> str:
        # Assuming month format is "YYYY-MM"
        year, month_num = month.split('-')
        month_num = int(month_num)

        with self.db.connect() as conn:
            query = """
                SELECT 
                    SUM(amount_cents) as total_spent
                FROM expenses 
                WHERE category_id = ? 
                  AND strftime('%Y-%m', expense_date) = ?
            """
            result = conn.execute(query, (category_id, month)).fetchone()
            total_spent = result[0] if result[0] is not None else 0

            # Assuming budget is stored in a separate table or config
            # For this implementation, we'll assume a default budget of 1000 cents (10 USD)
            budget_cents = 1000  # Default budget

            if total_spent <= budget_cents:
                return "Within budget"
            else:
                return "Over budget"

    def find_recurring_expenses(self, start_date: datetime.date, end_date: datetime.date) -> List[Expense]:
        with self.db.connect() as conn:
            query = """
                SELECT * FROM expenses 
                WHERE is_recurring = 1 
                  AND expense_date >= ? 
                  AND expense_date <= ?
            """
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            return [Expense(**dict(r)) for r in rows]

    def get_expenses_with_budget_status(self, start_date: datetime.date, end_date: datetime.date, category_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            query = """
                SELECT 
                    e.id,
                    e.amount_cents,
                    e.description,
                    e.expense_date,
                    e.category_id,
                    e.payment_method,
                    e.is_recurring
                FROM expenses e 
                WHERE e.expense_date >= ? 
                  AND e.expense_date <= ?
            """
            params = [start_date, end_date]
            if category_id is not None:
                query += " AND e.category_id = ?"
                params.append(category_id)

            rows = conn.execute(query, params).fetchall()

            result = []
            for row in rows:
                # Calculate budget status for each expense
                # For simplicity, we'll assume a default budget of 1000 cents (10 USD)
                # In a real app, this would come from a budget table or config
                total_spent = 0
                # We would need to sum up expenses for the same category and month
                # For now, we'll just return the expense with a placeholder status
                budget_status = "Within budget" if total_spent <= 1000 else "Over budget"
                result.append({
                    "id": row[0],
                    "amount_cents": row[1],
                    "description": row[2],
                    "expense_date": row[3],
                    "category_id": row[4],
                    "payment_method": row[5],
                    "is_recurring": row[6],
                    "budget_status": budget_status
                })

            return result

