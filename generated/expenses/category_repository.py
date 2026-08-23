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

    def get_expenses_by_category(self, category_id: int) -> List[Expense]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM expenses WHERE category_id = ?", (category_id,)
            ).fetchall()
            return [Expense(**dict(row)) for row in rows]

    def get_category_summary(self, category_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict[str, Any]:
        with self.db.connect() as conn:
            query = "SELECT SUM(amount) as total, COUNT(*) as count FROM expenses WHERE category_id = ?"
            params = [category_id]
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            rows = conn.execute(query, params).fetchone()
            return {
                "total_amount": rows[0] if rows[0] is not None else 0,
                "expense_count": rows[1] if rows[1] is not None else 0,
            }

    def get_category_budget_status(self, category_id: int, month: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            # Example: "2024-03" format
            month_year = month.strip()
            if not month_year:
                raise ValueError("Month must be provided in format 'YYYY-MM'")

            # Parse month and year
            try:
                year, month_part = month_year.split('-')
                year = int(year)
                month_num = int(month_part)
                if month_num < 1 or month_num > 12:
                    raise ValueError("Invalid month")
            except ValueError as e:
                raise ValueError(f"Invalid month format: {month_year}") from e

            # Query for expenses in that month
            query = """
                SELECT 
                    SUM(e.amount) as total_spent,
                    c.monthly_budget as budget
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE c.id = ? 
                  AND strftime('%Y-%m', e.date) = ?
            """
            params = [category_id, month_year]
            row = conn.execute(query, params).fetchone()
            total_spent = row[0] if row[0] is not None else 0
            budget = row[1] if row[1] is not None else 0

            return {
                "total_spent": total_spent,
                "budget": budget,
                "percentage_used": round((total_spent / budget) * 100 if budget > 0 else 0, 2),
                "is_over_budget": total_spent > budget
            }

