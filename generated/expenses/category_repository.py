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
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM expenses WHERE category_id = ? ORDER BY expense_date', (category_id,))
            rows = cursor.fetchall()
            return [Expense(**dict(r)) for r in rows]

    def get_category_summary(self, category_id: int, start_date: Optional[str]=None, end_date: Optional[str]=None) -> Dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM expenses WHERE category_id = ?'
            params = [category_id]
            if start_date:
                query += ' AND expense_date >= ?'
                params.append(start_date)
            if end_date:
                query += ' AND expense_date <= ?'
                params.append(end_date)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            total_amount_cents = sum((row[2] for row in rows))
            count = len(rows)
            return {'total_amount_cents': total_amount_cents, 'expense_count': count}

    def get_category_budget_status(self, category_id: int, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT b.amount_limit_cents, b.month, c.monthly_budget FROM budgets b JOIN categories c ON b.category_id = c.id WHERE b.category_id = ? AND b.month = ?', (category_id, month))
            row = cursor.fetchone()
            if row is None:
                return {'budget_limit_cents': 0, 'monthly_budget_cents': 0, 'is_over_budget': False}
            amount_limit_cents = row[0]
            monthly_budget_cents = row[2]
            total_spent = 0
            cursor.execute('SELECT SUM(amount_cents) FROM expenses WHERE category_id = ? AND expense_date BETWEEN ? AND ?', (category_id, month + '-01', month + '-31'))
            spent_row = cursor.fetchone()
            total_spent = spent_row[0] if spent_row[0] is not None else 0
            is_over_budget = total_spent > amount_limit_cents
            return {'budget_limit_cents': amount_limit_cents, 'monthly_budget_cents': monthly_budget_cents, 'is_over_budget': is_over_budget}

