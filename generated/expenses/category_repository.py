"""CategoryRepository data access."""
from __future__ import annotations

from datetime import date
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

    def list(self) -> List[Category]:
        return self.get_all()

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

    def find_expenses_by_category(self, category_id: int) -> List[Expense]:
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT e.id, e.amount, e.date, e.category_id FROM expenses e WHERE e.category_id = ?",
                (category_id,)
            ).fetchall()
            return [Expense(**dict(row)) for row in cur.fetchall()]

    def get_category_total_spending(self, category_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None) -> int:
        query = "SELECT SUM(e.amount) FROM expenses e WHERE e.category_id = ?"
        params = [category_id]

        if start_date:
            query += " AND e.date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND e.date <= ?"
            params.append(end_date)

        with self.db.connect() as conn:
            cur = conn.execute(query, params)
            total = cur.fetchone()[0]
            return total or 0

    def get_category_budget_status(self, category_id: int, month: str) -> str:
        # Example: "Under Budget", "On Budget", "Over Budget"
        # month format: "2024-03"
        try:
            year, month_num = month.split('-')
            month_num = int(month_num)
        except ValueError:
            raise ValueError("Invalid month format. Expected 'YYYY-MM'")

        # Get monthly budget
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT monthly_budget FROM categories WHERE id = ?",
                (category_id,)
            ).fetchone()
            monthly_budget = cur[0] if cur else 0

            # Get total spending for the month
            start_date = date(int(year), month_num, 1)
            end_date = date(int(year), month_num, 1) + date(1, 1, 1) - date(1, 1, 1)
            total_spending = self.get_category_total_spending(
                category_id=category_id,
                start_date=start_date,
                end_date=end_date
            )

            if total_spending < monthly_budget:
                return "Under Budget"
            elif total_spending == monthly_budget:
                return "On Budget"
            else:
                return "Over Budget"
        return "Unknown"

    def get_category_with_expenses(self, category_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict[str, Any]:
        with self.db.connect() as conn:
            # Fetch category details
            category_row = conn.execute(
                "SELECT * FROM categories WHERE id = ?",
                (category_id,)
            ).fetchone()
            if not category_row:
                raise CategoryNotFoundError(category_id)

            category = Category(**dict(category_row))

            # Fetch expenses for the category with optional date filtering
            expenses = self.find_expenses_by_category(category_id)

            # Filter expenses by date if provided
            if start_date and end_date:
                expenses = [e for e in expenses if start_date <= e.date <= end_date]
            elif start_date:
                expenses = [e for e in expenses if start_date <= e.date]
            elif end_date:
                expenses = [e for e in expenses if e.date <= end_date]

            return {
                "category": category,
                "expenses": expenses
            }

