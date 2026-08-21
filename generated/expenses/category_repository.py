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

    def find_expenses_for_category(self, category_id: int) -> List[Expense]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM expenses WHERE category_id = ?", (category_id,)
            ).fetchall()
            return [Expense(**dict(row)) for row in rows]

    def get_category_total_spending(self, category_id: int, start_date: date, end_date: date) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT SUM(amount) 
                FROM expenses 
                WHERE category_id = ? 
                  AND date >= ? 
                  AND date <= ?
                """,
                (category_id, start_date, end_date),
            )
            total = cur.fetchone()[0]
            return total or 0

    def get_category_spending_breakdown_by_month(self, category_id: int, start_date: date, end_date: date) -> Dict[str, int]:
        with self.db.connect() as conn:
            # Extract month-year from date and group by month
            rows = conn.execute(
                """
                SELECT 
                    strftime('%Y-%m', date) AS month,
                    SUM(amount) AS total_spent
                FROM expenses 
                WHERE category_id = ? 
                  AND date >= ? 
                  AND date <= ?
                GROUP BY strftime('%Y-%m', date)
                ORDER BY month
                """,
                (category_id, start_date, end_date),
            ).fetchall()
            return {
                row[0]: row[1] for row in rows
            }

    def get_category_budget_status(self, category_id: int, month: str) -> str:
        # Example: "Under Budget", "On Budget", "Over Budget"
        with self.db.connect() as conn:
            # Get total spending for the given month
            cur = conn.execute(
                """
                SELECT SUM(amount) AS total_spent
                FROM expenses 
                WHERE category_id = ? 
                  AND strftime('%Y-%m', date) = ?
                """,
                (category_id, month),
            )
            total_spent = cur.fetchone()[0] or 0

            # Get monthly budget from category
            category_row = conn.execute(
                "SELECT monthly_budget FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
            monthly_budget = category_row[0] if category_row else 0

            if total_spent < monthly_budget:
                return "Under Budget"
            elif total_spent == monthly_budget:
                return "On Budget"
            else:
                return "Over Budget"

