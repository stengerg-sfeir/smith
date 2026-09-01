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

    def list(self, amount_cents: Optional[Any] = None, category_id: Optional[Any] = None, description: Optional[Any] = None, expense_date: Optional[Any] = None, is_recurring: Optional[Any] = None, payment_method: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Expense]:
        with self.db.connect() as conn:
            query = "SELECT * FROM expenses WHERE 1=1"
            params: List[Any] = []
            if amount_cents is not None:
                query += ' AND amount_cents = ?'
                params.append(amount_cents)
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if expense_date is not None:
                query += ' AND expense_date = ?'
                params.append(expense_date)
            if is_recurring is not None:
                query += ' AND is_recurring = ?'
                params.append(is_recurring)
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
        return self.list(
            category_id=category_id,
        )

    def get_monthly_spending_summary(self, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT c.name, SUM(e.amount_cents) AS total_spent FROM expenses e JOIN categories c ON e.category_id = c.id WHERE substr(e.expense_date, 1, 7) = ? GROUP BY c.name', (month + '-01',)).fetchall()
            return [dict(name=row[0], total_spent=row[1]) for row in rows]

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT c.name, SUM(e.amount_cents) AS total_spent FROM expenses e JOIN categories c ON e.category_id = c.id WHERE substr(e.expense_date, 1, 4) = ? GROUP BY c.name', (str(year),)).fetchall()
            return [dict(name=row[0], total_spent=row[1]) for row in rows]

    def get_category_spending_range(self, category_id: int, start_date: date, end_date: date) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) AS v FROM expenses WHERE category_id = ? AND expense_date >= ? AND expense_date <= ?",
                (category_id, start_date, end_date)
            ).fetchone()
            return int(row["v"])

    def check_budget_exceeded(self, category_id: int, month: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute('SELECT amount_limit_cents FROM budgets WHERE category_id = ? AND month = ?', (category_id, month)).fetchone()
            if row is None:
                return False
            return row[0] < 0

    def get_budget_status_for_month(self, category_id: int, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM expenses r JOIN categories o ON r.category_id = o.id WHERE o.id = ?",
                (category_id,)
            ).fetchall()
            return [Expense(**dict(r)) for r in rows]

    def get_recurring_expense_patterns(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT e.description, e.amount_cents, e.payment_method, e.expense_date, c.name AS category_name FROM expenses e JOIN categories c ON e.category_id = c.id WHERE e.is_recurring = 1 ORDER BY e.expense_date').fetchall()
            return [dict(description=row[0], amount_cents=row[1], payment_method=row[2], expense_date=row[3], category_name=row[4]) for row in rows]

