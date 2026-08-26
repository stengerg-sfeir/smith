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

    def list(self, category_id: Optional[Any] = None, description: Optional[Any] = None, payment_method: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Expense]:
        with self.db.connect() as conn:
            query = "SELECT * FROM expenses WHERE 1=1"
            params: List[Any] = []
            if category_id is not None:
                query += ' AND category_id = ?'
                params.append(category_id)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
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
            cursor = conn.cursor()
            cursor.execute('SELECT c.name, SUM(e.amount_cents) AS total_spent FROM expenses e JOIN categories c ON e.category_id = c.id WHERE e.expense_date BETWEEN ? AND ? GROUP BY c.name', (month + '-01', month + '-31'))
            rows = cursor.fetchall()
            return [dict(name=row[0], total_spent=row[1]) for row in rows]

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT c.name, SUM(e.amount_cents) AS total_spent FROM expenses e JOIN categories c ON e.category_id = c.id WHERE e.expense_date BETWEEN ? AND ? GROUP BY c.name', (f'{year}-01-01', f'{year}-12-31'))
            rows = cursor.fetchall()
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
            cursor = conn.cursor()
            cursor.execute('SELECT b.amount_limit_cents FROM budgets b WHERE b.category_id = ? AND b.month = ?', (category_id, month))
            row = cursor.fetchone()
            if not row:
                return False
            limit_cents = row[0]
            cursor.execute('SELECT SUM(e.amount_cents) AS total_spent FROM expenses e WHERE e.category_id = ? AND e.expense_date BETWEEN ? AND ?', (category_id, month + '-01', month + '-31'))
            spent_row = cursor.fetchone()
            total_spent = spent_row[0] if spent_row[0] is not None else 0
            return total_spent > limit_cents

    def get_budget_status_for_month(self, category_id: int, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT b.amount_limit_cents, SUM(e.amount_cents) AS total_spent FROM budgets b LEFT JOIN expenses e ON e.category_id = b.category_id AND e.expense_date BETWEEN ? AND ? WHERE b.category_id = ? AND b.month = ? GROUP BY b.amount_limit_cents', (month + '-01', month + '-31', category_id, month))
            row = cursor.fetchone()
            if not row:
                return {'amount_limit_cents': 0, 'total_spent': 0}
            return {'amount_limit_cents': row[0], 'total_spent': row[1] if row[1] is not None else 0}

    def get_recurring_expense_patterns(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT e.description, e.category_id, e.payment_method, e.is_recurring, COUNT(*) AS frequency FROM expenses e WHERE e.is_recurring = 1 GROUP BY e.description, e.category_id, e.payment_method, e.is_recurring ORDER BY frequency DESC')
            rows = cursor.fetchall()
            return [dict(description=row[0], category_id=row[1], payment_method=row[2], is_recurring=row[3], frequency=row[4]) for row in rows]

