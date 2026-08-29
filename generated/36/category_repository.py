"""CategoryRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import CategoryNotFoundError
from models import Category


class CategoryRepository:
    """SQLite repository for Category over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, category: Category) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO categories (name, created_at, updated_at) VALUES (?, ?, ?)",
                (category.name, category.created_at, category.updated_at),
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
        allowed = ['name', 'created_at', 'updated_at']
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

    def get_category_by_name(self, category_name: str) -> Optional[Category]:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM categories WHERE name = ?', (category_name,)).fetchone()
            if row is None:
                return None
            return Category(**dict(row))

    def get_categories_with_product_count(self) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT c.id, c.name, c.created_at, c.updated_at, \n                (SELECT COUNT(*) FROM products WHERE products.category_id = c.id) AS product_count\n                FROM categories c\n                ORDER BY c.name\n            '.strip()).fetchall()
            return [dict(row) for row in rows]

    def get_active_categories(self) -> list[Category]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM categories WHERE updated_at >= '2024-01-01'").fetchall()
            return [Category(**dict(row)) for row in rows]

    def get_category_product_count(self, category_name: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM products p JOIN categories c ON p.category_id = c.id WHERE c.name = ?', (category_name,)).fetchone()
            return row[0] if row else 0

    def get_categories_by_product_price_range(self, min_price: float, max_price: float) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT DISTINCT c.id, c.name, c.created_at, c.updated_at\n                FROM categories c\n                JOIN products p ON c.id = p.category_id\n                WHERE p.price BETWEEN ? AND ?\n            '.strip()).fetchall()
            return [dict(row) for row in rows]

    def get_category_summary_by_price_band(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT category_id AS k, COUNT(*) AS n FROM products GROUP BY category_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

