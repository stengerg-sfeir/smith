"""CategoryRepository data access."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from database import Database
from models import Category, Product
from exceptions import CategoryNotFoundError


class CategoryRepository:
    """SQLite repository for Category over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, category: Category) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO categories (name, description, reorder_threshold) VALUES (?, ?, ?)",
                (category.name, category.description, category.reorder_threshold),
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

    def list(self, description: Optional[Any] = None, name: Optional[Any] = None, reorder_threshold: Optional[Any] = None) -> List[Category]:
        with self.db.connect() as conn:
            query = "SELECT * FROM categories WHERE 1=1"
            params: List[Any] = []
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if reorder_threshold is not None:
                query += ' AND reorder_threshold = ?'
                params.append(reorder_threshold)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Category(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'description', 'reorder_threshold']
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

    def create(self, category: Category) -> int:
        return 0

    def get_by_id(self, id: int) -> Optional[Category]:
        return None

    def list_all(self) -> list[Category]:
        return []

    def find_products_by_category(self, category_id: int) -> list[Product]:
        return []

