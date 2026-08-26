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
        raise NotImplementedError()

    def get_categories_with_product_count(self) -> list[dict[str, any]]:
        raise NotImplementedError()

    def get_active_categories(self) -> list[Category]:
        raise NotImplementedError()

    def get_category_product_count(self, category_name: str) -> int:
        raise NotImplementedError()

    def get_categories_by_product_price_range(self, min_price: float, max_price: float) -> list[dict[str, any]]:
        raise NotImplementedError()

    def get_category_summary_by_price_band(self) -> dict[str, int]:
        raise NotImplementedError()

