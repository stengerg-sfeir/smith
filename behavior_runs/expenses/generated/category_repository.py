"""CategoryRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CategoryNotFoundError
from models import Category, Expense


class CategoryRepository:
    """SQLite repository for Category over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, category: Category) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO categories (name, description, monthly_budget, icon) VALUES (?, ?, ?, ?)",
                (category.name, category.description, category.monthly_budget, category.icon),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Category]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM categories WHERE id = ?", (id,)
            ).fetchone()
            return Category(**dict(row)) if row else None

    def get_all(self) -> List[Category]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM categories ORDER BY id"
            ).fetchall()
            return [Category(**dict(r)) for r in rows]

    def list(self, description: Optional[Any] = None, icon: Optional[Any] = None, monthly_budget: Optional[Any] = None, name: Optional[Any] = None) -> List[Category]:
        with self.db.connect() as conn:
            query = "SELECT * FROM categories WHERE 1=1"
            params: List[Any] = []
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if icon is not None:
                query += ' AND icon = ?'
                params.append(icon)
            if monthly_budget is not None:
                query += ' AND monthly_budget = ?'
                params.append(monthly_budget)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Category(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'monthly_budget', 'icon']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE categories SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise CategoryNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM categories WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_expenses_by_category(self, category_id: int) -> List[Expense]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM expenses WHERE category_id = ?'
            rows = conn.execute(query, (category_id,)).fetchall()
            return [Expense(**dict(r)) for r in rows]

    def get_category_summary(self, category_id: int, start_date: Optional[str]=None, end_date: Optional[str]=None) -> Dict[str, Any]:
        with self.db.connect() as conn:
            query = 'SELECT * FROM expenses WHERE category_id = ?'
            params = [category_id]
            conditions = []
            if start_date:
                conditions.append('expense_date >= ?')
                params.append(start_date)
            if end_date:
                conditions.append('expense_date <= ?')
                params.append(end_date)
            if conditions:
                query += ' AND ' + ' AND '.join(conditions)
            query += ' ORDER BY expense_date'
            rows = conn.execute(query, params).fetchall()
            total_amount_cents = sum((row[2] for row in rows))
            count = len(rows)
            return {'total_amount_cents': total_amount_cents, 'expense_count': count}

    def get_category_budget_status(self, category_id: int, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            budget_query = 'SELECT amount_limit_cents FROM budgets WHERE category_id = ? AND month = ?'
            budget_row = conn.execute(budget_query, (category_id, month)).fetchone()
            expense_query = '\n                SELECT SUM(amount_cents) AS total_expenses_cents \n                FROM expenses \n                WHERE category_id = ? \n                AND expense_date LIKE ?\n            '
            expense_row = conn.execute(expense_query, (category_id, f'{month}-%')).fetchone()
            total_expenses_cents = expense_row[0] if expense_row[0] is not None else 0
            if budget_row is None:
                budget_limit_cents = 0
            else:
                budget_limit_cents = budget_row[0]
            usage_percentage = total_expenses_cents / budget_limit_cents * 100 if budget_limit_cents > 0 else 0
            return {'budget_limit_cents': budget_limit_cents, 'total_expenses_cents': total_expenses_cents, 'usage_percentage': round(usage_percentage, 2)}

