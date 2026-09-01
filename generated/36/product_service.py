"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from category_repository import CategoryRepository
from database import Database
from models import Category
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.product_repo = ProductRepository(db)

    def add_category(self, name: str) -> None:
        category = Category(name=name, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.category_repo.create(category)

    def list_category(self) -> list[dict]:
        results = {}
        for row in self.category_repo.list():
            key = row.name
            results[key] = results.get(key, 0) + row.id
        return results

    def list_product(self, name: Optional[str] = None, price: Optional[str] = None, category_id: Optional[str] = None) -> list[dict]:
        return self.product_repo.list(name=name, price=price, category_id=category_id)

    def delete_category(self, id: int) -> None:
        return self.category_repo.delete(id)

    def update_category(self, id: int, name: str) -> None:
        data = {k: v for k, v in {'name': name}.items() if v is not None}
        return self.category_repo.update(id, data)

