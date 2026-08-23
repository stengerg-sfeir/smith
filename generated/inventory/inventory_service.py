"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from category_repository import CategoryRepository
from database import Database
from exceptions import CategoryNotFoundError
from models import Product
from product_repository import ProductRepository


class InventoryService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.product_repo = ProductRepository(db)

    def add_product(self, sku: str, name: str, category_id: int, price_cents: int, stock_qty: int) -> None:
        if category_id is not None:
            if self.category_repo.get_by_id(category_id) is None:
                raise CategoryNotFoundError(category_id)
        product = Product(sku=sku, name=name, category_id=category_id, price_cents=price_cents, stock_qty=stock_qty)
        return self.product_repo.create(product)

    def update_product(self, id: int, data: Dict[str, Any]) -> None:
        self.product_repo.update(id, data)

    def delete_product(self, id: int) -> None:
        return self.product_repo.delete(id)

    def get_product_by_id(self, id: int) -> Optional[Product]:
        return self.product_repo.get_by_id(id)

    def list_products(self, category_id: Optional[int] = None, low_only: Optional[bool] = None) -> List[Product]:
        return self.product_repo.list(category_id=category_id, low_only=low_only)

    def restock(self, id: int, qty: int) -> None:
        raise NotImplementedError()

    def low_stock_report(self) -> List[Product]:
        raise NotImplementedError()

    def stock_value_by_category(self) -> Dict[str, int]:
        results = {}
        for row in self.product_repo.list():
            key = row.category_id
            results[key] = results.get(key, 0) + row.price_cents
        return results

